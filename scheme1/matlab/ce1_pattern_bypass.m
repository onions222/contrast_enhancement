function result = ce1_pattern_bypass(histogram32, total_pixels, cfg)
%CE1_PATTERN_BYPASS 基于直方图拓扑的 pattern bypass 检测。
% 目标：
%   - 用统一的 mask / A / C / R / F / Pmax 特征替代旧的 dense/sparse/comb 三路判定
%   - 只保留整数运算，便于映射到 RTL
%   - 判断重点不是“图像主观上好不好看”，而是“这帧是否更像测试 pattern”
%   - 若更像测试 pattern，则当前帧不应再进入 CE 主路径，而应直接走 identity LUT
%
% 输入：
%   histogram32 : 32 x 1 uint32，32-bin 粗直方图
%   total_pixels: uint32，帧总像素数
%   cfg         : struct，必选输入，需包含 topology bypass 阈值字段
%
% 输出：
%   result.bypass_flag      : uint8，1 = bypass，0 = 正常增强
%   result.bypass_reason    : char，'uniform_sparse' / 'narrow_continuous_transition' / ...
%   result.active_count     : uint8，活跃 bin 数 A
%   result.connectivity_count : uint8，相邻活跃对数 C
%   result.run_count        : uint8，连续段数 R = A - C
%   result.span_count       : uint8，活跃跨度 F
%   result.first_active_bin : uint8
%   result.last_active_bin  : uint8
%   result.max_bin_count    : uint32，最大单 bin 计数 Pmax
%   result.extrema_count    : uint8，活跃区内部峰谷个数
%   result.edge_pair_count  : uint8，相邻 bin 对中至少一端接近峰值的对数
%   result.plateau_pair_count : uint8，相邻 bin 对差分很小的对数
%   result.active_mask      : 32 x 1 uint8，每位都是 U1.0 的活跃掩码
%   result.threshold_count  : uint32，活跃门限

n_bins = int32(cfg.pattern_hist_bin_count);

% 这些寄存器/局部量共同描述 32-bin 直方图的拓扑结构。
% active_mask        : 32 x U1.0，每个位置只保留“该 bin 是否显著活跃”的 0/1 信息。
% active_count (A)   : U6.0，范围 0~32，一共有多少个活跃 bin。
% connectivity_count (C): U6.0，范围 0~31，有多少对相邻 bin 同时活跃。
% run_count (R)      : U6.0，范围 0~32，活跃 bin 被切成多少段连续区间。
% span_count (F)     : U6.0，范围 0~32，从 first_active 到 last_active 的覆盖宽度。
% first/last_active_bin: U5.0，范围 0~31，活跃区首尾索引。
% max_bin_count (Pmax): Uceil(log2(TotalPixels+1)).0，单个 bin 的最大计数。
active_mask = zeros(n_bins, 1, 'uint8');
active_count = uint8(0);
connectivity_count = uint8(0);
run_count = uint8(0);
span_count = uint8(0);
first_active_bin = uint8(0);
last_active_bin = uint8(0);
max_bin_count = uint32(0);
extrema_count = uint8(0);
edge_pair_count = uint8(0);
plateau_pair_count = uint8(0);
% found_first / prev_active: U1.0，局部状态位。
found_first = uint8(0);
prev_active = uint8(0);

% threshold_count 是 active mask 的门限。
% 这里不要求 bin 只要非零就算活跃，而是要求 bin 计数超过一个极小占比阈值。
% 目的：
%   - 过滤单点噪声、孤立异常像素、极少量坏点污染
%   - 只保留真正能代表“分布形状”的 bin
% 位宽：
%   - threshold_count: Uceil(log2(TotalPixels+1)).0
threshold_count = bitshift(uint32(total_pixels), -int32(cfg.pattern_active_threshold_shift));

if cfg.pattern_bypass_enable == uint8(0)
    % bypass 关闭时，直接返回空命中结果。
    % 这里仍然把所有特征字段带出去，是为了保证上层接口结构固定。
    result = struct();
    result.bypass_flag = uint8(0);
    result.bypass_reason = '';
    result.active_count = active_count;
    result.connectivity_count = connectivity_count;
    result.run_count = run_count;
    result.span_count = span_count;
    result.first_active_bin = first_active_bin;
    result.last_active_bin = last_active_bin;
    result.max_bin_count = max_bin_count;
    result.extrema_count = extrema_count;
    result.edge_pair_count = edge_pair_count;
    result.plateau_pair_count = plateau_pair_count;
    result.active_mask = uint8(active_mask(:));
    result.threshold_count = uint32(threshold_count);
    return;
end

% Stage 1: 扫描 32-bin histogram，生成 active mask 与基础拓扑特征。
% 这一段只做最基础的结构统计，不做任何 bypass 决策。
% 先把图像分布抽象成“哪些 bin 活跃、活跃区如何连通”。
% bin_index: S6.0，本地循环索引，对应 0~31 的 bin 地址。
bin_index = int32(0);
while bin_index < n_bins
    % count: Uceil(log2(TotalPixels+1)).0，当前 bin 计数。
    count = uint32(histogram32(bin_index + 1));
    % current_active: U1.0，当前 bin 是否进入 active mask。
    current_active = uint8(0);

    % Pmax 需要在全局 32 个 bin 上取最大值。
    % 后续连续型规则会用它衡量“是不是过于均匀地铺开”。
    if count > max_bin_count
        max_bin_count = count;
    end

    % 只有超过 threshold_count 的 bin 才进入 active mask。
    if count > threshold_count
        current_active = uint8(1);
        active_mask(bin_index + 1) = uint8(1);
        active_count = active_count + uint8(1);
        last_active_bin = uint8(bin_index);

        % first_active_bin 只在首次命中时锁存。
        % 这样最后就能和 last_active_bin 一起给出活跃跨度。
        if found_first == uint8(0)
            first_active_bin = uint8(bin_index);
            found_first = uint8(1);
        end

        % 若当前活跃 bin 和前一个 bin 连在一起，则 C 加 1。
        % 否则说明进入了新的连续段，R 加 1。
        % 这就是为什么最终有 R = A - C。
        if prev_active == uint8(1)
            connectivity_count = connectivity_count + uint8(1);
        else
            run_count = run_count + uint8(1);
        end
    end

    prev_active = current_active;
    bin_index = bin_index + int32(1);
end

if active_count > uint8(0)
    % F = last_active - first_active + 1。
    % 它表示整段活跃分布在 32-bin 域里横跨了多宽。
    span_count = uint8(int32(last_active_bin) - int32(first_active_bin) + 1);
end

if active_count > uint8(0)
    % Stage 2: 在活跃区内部继续提取“形状特征”。
    % 这些特征不改变主拓扑框架，只用于连续型分布的后续细分。
    %
    % peak_half_threshold:
    %   取 Pmax 的一半，后续用它定义“接近峰值”的高计数区域。
    % 位宽：
    %   - peak_half_threshold: Uceil(log2(TotalPixels+1)).0
    peak_half_threshold = idivide(uint32(max_bin_count + uint32(1)), uint32(2), 'floor');

    % Stage 2.1: 统计 plateau_pair_count 和 edge_pair_count。
    %
    % plateau_pair_count:
    %   统计相邻 bin 对中，差分绝对值足够小的 pair 数量。
    %   它反映活跃区是否存在较长“平台”或近似恒定段。
    %
    % edge_pair_count:
    %   统计相邻 bin 对中，至少一端已经接近峰值的 pair 数量。
    %   它用来描述高计数区域是不是集中在很少数位置。
    % local_index: S6.0，本地活跃区索引。
    local_index = int32(first_active_bin);
    while local_index < int32(last_active_bin)
        % left_value / right_value: Uceil(log2(TotalPixels+1)).0，相邻两个 bin 计数。
        left_value = uint32(histogram32(local_index + 1));
        right_value = uint32(histogram32(local_index + 2));

        % 相邻 pair 的绝对差分。
        % 若差分很小，说明这两个 bin 落在一个近似平台段上。
        % diff_value: S(ceil(log2(TotalPixels+1))+1).0，先做有符号减法，再取绝对值。
        diff_value = int32(left_value) - int32(right_value);
        if diff_value < int32(0)
            diff_value = -diff_value;
        end
        if uint32(diff_value) <= uint32(cfg.pattern_special_plateau_diff_max)
            plateau_pair_count = plateau_pair_count + uint8(1);
        end

        % 若 pair 中任一端已经接近全局峰值，则认为它属于“高计数邻接对”。
        % 对某些特殊测试图，这个量会明显偏小或偏集中。
        if left_value >= peak_half_threshold || right_value >= peak_half_threshold
            edge_pair_count = edge_pair_count + uint8(1);
        end

        local_index = local_index + int32(1);
    end

    % Stage 2.2: 统计 extrema_count。
    % 这里的 extrema_count 不是几何边缘数，而是直方图一维序列里的局部峰谷数。
    % 直观上：
    %   - 平滑 ramp / 某些人工连续图，extrema_count 往往很低
    %   - 自然宽分布，通常会有更多起伏，因此 extrema_count 更高
    local_index = int32(first_active_bin) + int32(1);
    while local_index <= int32(last_active_bin) - int32(1)
        % prev/curr/next_value: Uceil(log2(TotalPixels+1)).0，三点比较窗口。
        prev_value = uint32(histogram32(local_index));
        curr_value = uint32(histogram32(local_index + 1));
        next_value = uint32(histogram32(local_index + 2));

        % 只要当前 bin 相对前后形成局部峰或局部谷，就记为一个 extrema。
        % is_extrema: U1.0，单周期判决位。
        is_extrema = uint8(0);
        if (curr_value > prev_value && curr_value >= next_value) || ...
           (curr_value >= prev_value && curr_value > next_value) || ...
           (curr_value < prev_value && curr_value <= next_value) || ...
           (curr_value <= prev_value && curr_value < next_value)
            is_extrema = uint8(1);
        end

        if is_extrema == uint8(1)
            extrema_count = extrema_count + uint8(1);
        end

        local_index = local_index + int32(1);
    end
end

bypass_flag = uint8(0);
bypass_reason = '';

% Rule 1: Uniform / Sparse
% 这条规则先抓最简单、最确定的一类。
% 若 A <= 2，说明只有 1~2 个活跃 bin，图像本质上接近纯色或极简分布。
% 这类图没有进入 CE 的意义，直接 bypass。
if active_count <= uint8(cfg.pattern_uniform_sparse_active_max)
    bypass_flag = uint8(1);
    bypass_reason = 'uniform_sparse';
end

% Rule 1.5: Narrow Continuous Transition
% 这条规则专门抓“窄连续过渡”。
% 特征是：
%   - 只有一段连续活跃区，R == 1
%   - 活跃 bin 数和跨度都很小，说明只在很窄亮度范围内平滑变化
%   - Pmax 不应过大，否则更像局部峰值聚集，而不是过渡图
% 典型对象：
%   - near-black ramp
%   - near-white ramp
%   - shallow ramp
if bypass_flag == uint8(0)
    % narrow_gate: U1.0，Rule 1.5 的局部使能位。
    narrow_gate = uint8(1);
    if run_count ~= uint8(1)
        narrow_gate = uint8(0);
    end
    if active_count > uint8(cfg.pattern_narrow_continuous_active_max)
        narrow_gate = uint8(0);
    end
    if span_count > uint8(cfg.pattern_narrow_continuous_span_max)
        narrow_gate = uint8(0);
    end
    if narrow_gate == uint8(1)
        % lhs_peak / rhs_peak: 扩展位宽乘法比较中间量。
        % 这里直接表达算法约束，不再模拟除法器或额外软件保护。
        lhs_peak = int64(max_bin_count) * int64(cfg.pattern_narrow_continuous_peak_denom);
        rhs_peak = int64(total_pixels);
        if lhs_peak <= rhs_peak
            bypass_flag = uint8(1);
            bypass_reason = 'narrow_continuous_transition';
        end
    end
end

% Rule 2: Disconnected / Comb
% 这条规则抓“断断续续的离散结构”。
% 公式 R * K > A 的直觉是：
%   - A 表示一共有多少个活跃 bin
%   - R 表示这些活跃 bin 被切成多少段
% 若 R 相对 A 过大，说明分布不是连成一片，而是被切成很多离散小段。
% 典型对象：
%   - color bars
%   - step16
%   - checker / stripe / dot-matrix
if bypass_flag == uint8(0)
    % lhs_runs / rhs_runs: 扩展位宽的 run-density 比较中间量。
    lhs_runs = int32(run_count) * int32(cfg.pattern_disconnected_comb_runs_mul);
    rhs_runs = int32(active_count);
    if lhs_runs > rhs_runs
        bypass_flag = uint8(1);
        bypass_reason = 'disconnected_comb';
    end
end

% Rule 3: Continuous Artificial
% 这条规则抓“宽连续且过于规整”的人工图。
% 前提是：
%   - R == 1，说明整段连续
%   - A / F 足够大，说明覆盖范围很宽
%   - extrema_count 很小，说明内部起伏不多
% 然后再用 Pmax 做均匀性约束：
%   - 若 Pmax 不高，说明整段分布更像均匀铺开，而不是自然图那种峰值集中
if bypass_flag == uint8(0)
    % continuous_gate: U1.0，Rule 3 的局部使能位。
    continuous_gate = uint8(1);
    if run_count ~= uint8(1)
        continuous_gate = uint8(0);
    end
    if int32(active_count) < int32(cfg.pattern_continuous_active_min)
        continuous_gate = uint8(0);
    end
    if int32(span_count) < int32(cfg.pattern_continuous_span_min)
        continuous_gate = uint8(0);
    end
    if extrema_count > uint8(cfg.pattern_continuous_extrema_max)
        continuous_gate = uint8(0);
    end
    if continuous_gate == uint8(1)
        % lhs_peak / rhs_peak: 扩展位宽乘法比较中间量。
        lhs_peak = int64(max_bin_count) * int64(cfg.pattern_continuous_peak_denom);
        rhs_peak = int64(total_pixels);
        if lhs_peak <= rhs_peak
            bypass_flag = uint8(1);
            bypass_reason = 'continuous_artificial';
        end
    end
end

% Rule 4: Special Continuous Artificial
% 这条规则是后置补充分支。
% 它只在前面四条都未命中时才有机会生效，因此可以在后续硬件实现阶段单独删除。
% 目标不是重定义主 bypass，而是补抓两类很特殊的连续测试图：
%   - circular gradient
%   - gradient with stripes
%
% 这里拆成两个子形态：
% 1. smooth_wide_special
%    - extrema 很少
%    - Pmax 仍然不高
%    - 更像非常平滑、非常规整的宽连续图
%
% 2. plateau_edge_special
%    - extrema 可以略多
%    - 但平台 pair 很多，说明大段近似平坦
%    - 同时 edge_pair_count 又很小，说明高计数区并没有在很多位置展开
%    - 更适合补抓“长平台 + 端点异常”的特殊 pattern
if bypass_flag == uint8(0)
    % special_gate: U1.0，后置特殊分支的总使能位。
    special_gate = uint8(1);
    if run_count ~= uint8(1)
        special_gate = uint8(0);
    end
    if int32(active_count) < int32(cfg.pattern_special_continuous_active_min)
        special_gate = uint8(0);
    end
    if int32(span_count) < int32(cfg.pattern_special_continuous_span_min)
        special_gate = uint8(0);
    end
    if special_gate == uint8(1)
        % 子形态 1：平滑宽连续图。
        % smooth_wide_special: U1.0，子形态 1 命中位。
        smooth_wide_special = uint8(0);
        lhs_peak = int64(max_bin_count) * int64(cfg.pattern_special_continuous_peak_denom);
        rhs_peak = int64(total_pixels);
        if extrema_count <= uint8(cfg.pattern_special_continuous_extrema_max) && lhs_peak <= rhs_peak
            smooth_wide_special = uint8(1);
        end

        % 子形态 2：平台主导、边缘集中很弱的连续图。
        % plateau_edge_special: U1.0，子形态 2 命中位。
        plateau_edge_special = uint8(0);
        if extrema_count <= uint8(cfg.pattern_special_plateau_extrema_max) && ...
           plateau_pair_count >= uint8(cfg.pattern_special_plateau_pair_min) && ...
           edge_pair_count <= uint8(cfg.pattern_special_edge_pair_max)
            plateau_edge_special = uint8(1);
        end

        % 两个子形态只要命中任意一个，就统一归到 special_continuous_artificial。
        if smooth_wide_special == uint8(1) || plateau_edge_special == uint8(1)
            bypass_flag = uint8(1);
            bypass_reason = 'special_continuous_artificial';
        end
    end
end

% 输出阶段只做字段打包，不再改变任何决策结果。
% 上层控制路径会根据 bypass_flag 决定是否直接输出 identity LUT。
result = struct();
result.bypass_flag = bypass_flag;
result.bypass_reason = bypass_reason;
result.active_count = active_count;
result.connectivity_count = connectivity_count;
result.run_count = run_count;
result.span_count = span_count;
result.first_active_bin = first_active_bin;
result.last_active_bin = last_active_bin;
result.max_bin_count = max_bin_count;
result.extrema_count = extrema_count;
result.edge_pair_count = edge_pair_count;
result.plateau_pair_count = plateau_pair_count;
result.active_mask = uint8(active_mask(:));
result.threshold_count = uint32(threshold_count);
end
