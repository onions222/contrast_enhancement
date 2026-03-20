function result = ce1_pattern_bypass(histogram32, total_pixels, cfg)
%CE1_PATTERN_BYPASS 三路直方图 pattern bypass 检测。
% 设计动机：
%   - 方案一的主路径面向自然图像增强，假设输入分布来自真实场景
%   - 但 DDIC 实际应用里会遇到大量“非自然输入”，例如 ramp、color bar、gray step、
%     stripe、dot matrix、window pattern、纯色工模等
%   - 这些 pattern 的目标不是“看起来更有层次”，而是“保持原始码值关系不变”
%   - 因此控制路径需要在生成 PWL 之前先做一层 pattern 识别，命中后直接 bypass
%
% 实现原则：
%   - 只用 32-bin 粗直方图，不用空间特征
%   - 完全使用整数运算，可直接映射到硬件寄存器和比较器
%   - 三路判定分别覆盖 dense / sparse / comb 三类典型测试图分布
%   - 只要任一路命中，就输出 bypass_flag = 1
%
% 输入：
%   histogram32 : 32 x 1 uint32，粗直方图（bin_shift = 3）
%   total_pixels: uint32，帧总像素数
%   cfg         : struct，来自 ce1_hw_config，需含 pattern_* 字段
%
% 输出：
%   result : struct
%     .bypass_flag         : uint8，1 = 命中 bypass，0 = 正常增强
%     .bypass_reason       : char，命中原因（'dense' / 'sparse' / 'comb' / ''）
%     .active_bin_count    : uint8，非零 bin 数
%     .first_active_bin    : uint8，最低非零 bin 索引
%     .last_active_bin     : uint8，最高非零 bin 索引
%     .span_bin_count      : uint8，first ~ last 之间的跨度（含两端）
%     .hole_count          : uint8，span 内的空 bin 数
%     .active_run_count    : uint8，连续非零 bin 段数
%     .max_bin_count       : uint32，单 bin 最大计数
%     .sum_abs_diff        : uint32，相邻 bin 差分绝对值之和
%     .sum_active_count    : uint32，所有非零 bin 的计数总和

if nargin < 3 || isempty(cfg)
    cfg = ce1_hw_config();
end

n_bins = int32(cfg.pattern_hist_bin_count);  % 32

% ---------------------------------------------------------------
% Step 1: 特征提取 —— 扫描 32 个 bin，提取帧级直方图结构量
% ---------------------------------------------------------------
% 这一阶段不做 bypass 决策，只把后续三路判定需要的“结构特征”提取出来。
% 这些特征都可以理解为对 32-bin histogram 形状的压缩描述。
%
% 核心特征的工程含义：
%   - active_bin_count: 有多少个 bin 非零。越少，越像纯色/step/bar 这类离散 pattern。
%   - first_active_bin / last_active_bin: 有效分布落在什么灰度区间。
%   - span_bin_count: 首尾非零 bin 包住的跨度。用于区分“窄聚集”和“长跨度 pattern”。
%   - hole_count: 在首尾跨度内部有多少空洞。hole 多说明直方图更像梳状/离散分布。
%   - active_run_count: 非零 bin 被分成几段。run 多说明有周期性间断。
%   - max_bin_count: 最大峰值有多高。对纯色/近纯色帧很敏感。
%   - sum_abs_diff: 相邻 bin 起伏总量。对 dense gradient 的平滑程度敏感。

% active_mask: 32 x 1 逻辑向量，标记非零 bin。
active_mask = zeros(n_bins, 1, 'uint8');

% active_bin_count: U6.0，非零 bin 计数。
active_bin_count = uint8(0);
% first_active_bin / last_active_bin: U5.0，首尾非零 bin 索引（0-based）。
first_active_bin = uint8(0);
last_active_bin = uint8(0);
found_first = uint8(0);
% max_bin_count: Uceil(log2(Npix)).0，单 bin 最大计数。
max_bin_count = uint32(0);
% sum_active_count: U32.0，所有非零 bin 的计数之和。
sum_active_count = uint32(0);

bin_index = int32(0);
while bin_index < n_bins
    count = uint32(histogram32(bin_index + 1));
    if count > uint32(0)
        active_mask(bin_index + 1) = uint8(1);
        active_bin_count = active_bin_count + uint8(1);
        last_active_bin = uint8(bin_index);
        sum_active_count = sum_active_count + count;
        if found_first == uint8(0)
            first_active_bin = uint8(bin_index);
            found_first = uint8(1);
        end
    end
    if count > max_bin_count
        max_bin_count = count;
    end
    bin_index = bin_index + int32(1);
end

% span_bin_count: U5.0，first ~ last 区间长度（含两端）。
% 若 active_bin_count 很小但 span 很大，说明中间存在明显 hole，更像 comb / step pattern。
if active_bin_count > uint8(0)
    span_bin_count = uint8(int32(last_active_bin) - int32(first_active_bin) + 1);
else
    span_bin_count = uint8(0);
end

% hole_count: U5.0，span 内的空洞数。
% 计算方式：
%   hole_count = span_bin_count - active_bin_count
% 如果首尾之间大部分 bin 都是空的，hole_count 会明显变大。
hole_count = uint8(int32(span_bin_count) - int32(active_bin_count));

% active_run_count: U5.0，连续非零 bin 段数。
% 这个量用于衡量“非零 bin 是一整段连续分布，还是被拆成很多离散小段”。
active_run_count = uint8(0);
run_len = uint8(0);
bin_index = int32(0);
while bin_index < n_bins
    if active_mask(bin_index + 1) == uint8(1)
        run_len = run_len + uint8(1);
        if run_len == uint8(1)
            active_run_count = active_run_count + uint8(1);
        end
    else
        run_len = uint8(0);
    end
    bin_index = bin_index + int32(1);
end

% sum_abs_diff: U32.0，相邻 bin 差分绝对值之和。
% 这个量越小，说明 histogram 越平滑、越像连续 gradient。
% 这个量越大，说明 histogram 起伏剧烈，更像离散条带或稀疏 pattern。
sum_abs_diff = uint32(0);
bin_index = int32(1);
while bin_index < n_bins
    a = int64(histogram32(bin_index));      % bin[i-1]
    b = int64(histogram32(bin_index + 1));  % bin[i]
    diff_val = b - a;
    if diff_val < int64(0)
        diff_val = -diff_val;
    end
    sum_abs_diff = sum_abs_diff + uint32(diff_val);
    bin_index = bin_index + int32(1);
end

% ---------------------------------------------------------------
% Step 2: 三路判定
% ---------------------------------------------------------------
% 判定顺序为 dense -> sparse -> comb。
% 原因：
%   - dense gradient 往往 active bin 很多，形状最容易和自然图像接近，优先判掉可减少误增强
%   - sparse pattern 其次，主要针对少数离散灰阶的工模
%   - comb pattern 最后，主要针对长跨度但内部大量空洞的梳状分布
% 一旦某一路命中，后续分支不再继续覆盖其结果。

bypass_flag = uint8(0);
bypass_reason = '';

if cfg.pattern_bypass_enable == uint8(0)
    % bypass 功能被寄存器禁用时，直接跳过判定。
    result = struct();
    result.bypass_flag = uint8(0);
    result.bypass_reason = '';
    result.active_bin_count = active_bin_count;
    result.first_active_bin = first_active_bin;
    result.last_active_bin = last_active_bin;
    result.span_bin_count = span_bin_count;
    result.hole_count = hole_count;
    result.active_run_count = active_run_count;
    result.max_bin_count = max_bin_count;
    result.sum_abs_diff = sum_abs_diff;
    result.sum_active_count = sum_active_count;
    return;
end

% --- Branch 1: Dense Gradient ---
% 条件：
%   active_bin_count >= pattern_dense_active_min
%   span_bin_count   >= pattern_dense_span_min
%   active_run_count <= pattern_dense_runs_max
%   hole_count       <= pattern_dense_holes_max
%   sum_abs_diff * active_bin_count * flatness_denom <= flatness_numer * sum_active_count
%
% 工程含义：
%   - active_bin_count 多、span 大，说明分布不是“几根孤立尖峰”
%   - run 少、hole 少，说明非零 bin 基本连续
%   - flatness 条件限制相邻 bin 起伏不能太剧烈，避免自然纹理场景被误判成 gradient
% 典型命中：
%   - linear ramp
%   - smooth gradient
%   - near-black / near-white smooth ramp
%   - 某些非常规则、接近连续分布的 pattern
dense_ok = uint8(1);
if int32(active_bin_count) < int32(cfg.pattern_dense_active_min)
    dense_ok = uint8(0);
end
if int32(span_bin_count) < int32(cfg.pattern_dense_span_min)
    dense_ok = uint8(0);
end
if int32(active_run_count) > int32(cfg.pattern_dense_runs_max)
    dense_ok = uint8(0);
end
if int32(hole_count) > int32(cfg.pattern_dense_holes_max)
    dense_ok = uint8(0);
end
if dense_ok == uint8(1)
    % flatness 判定使用交叉乘法避免除法。
    % 若把 flatness 简化理解成：
    %   average_abs_diff = sum_abs_diff / active_bin_count
    % 则这里的交叉乘法本质上是在比较：
    %   average_abs_diff <= (flatness_numer / flatness_denom) * average_bin_mass
    % 即“相邻 bin 的平均起伏”不能太大。
    lhs = int64(sum_abs_diff) * int64(active_bin_count) * int64(cfg.pattern_dense_flatness_denom);
    rhs = int64(cfg.pattern_dense_flatness_numer) * int64(max(sum_active_count, uint32(1)));
    if lhs > rhs
        dense_ok = uint8(0);
    end
end
if dense_ok == uint8(1)
    bypass_flag = uint8(1);
    bypass_reason = 'dense';
end

% --- Branch 2: Sparse Pattern ---
% 条件：
%   active_bin_count <= pattern_sparse_active_max
%   max_bin_count * sparse_peak_denom <= total_pixels * sparse_peak_numer
%
% 工程含义：
%   - 先要求 active_bin_count 少，说明分布只占据少数几个灰阶桶
%   - 再限制最大峰值不能过高，避免把“几乎纯色的一帧自然图像”都粗暴归到 sparse pattern
%   - 这一支更像是在捕获“少数离散台阶构成的规则图”
% 典型命中：
%   - SMPTE bars
%   - RGB/EBU color bars
%   - gray step wedge
%   - 单通道 stepped ramp
%   - 若阈值设得更宽，也可能覆盖纯色/近纯色工模
if bypass_flag == uint8(0)
    sparse_ok = uint8(1);
    if int32(active_bin_count) > int32(cfg.pattern_sparse_active_max)
        sparse_ok = uint8(0);
    end
    if sparse_ok == uint8(1)
        lhs_sp = int64(max_bin_count) * int64(cfg.pattern_sparse_peak_denom);
        rhs_sp = int64(total_pixels) * int64(cfg.pattern_sparse_peak_numer);
        if lhs_sp > rhs_sp
            sparse_ok = uint8(0);
        end
    end
    if sparse_ok == uint8(1)
        bypass_flag = uint8(1);
        bypass_reason = 'sparse';
    end
end

% --- Branch 3: Comb Pattern ---
% 条件：
%   span_bin_count    >= pattern_comb_span_min
%   hole_count * comb_hole_denom >= span_bin_count * comb_hole_numer
%   active_run_count  >= pattern_comb_runs_min
%   max_bin_count     < total_pixels
%
% 工程含义：
%   - span 大：说明分布覆盖了较长灰度区间
%   - hole 比例高：说明中间很多 bin 为空，呈明显梳状
%   - run 数多：说明非零 bin 被拆成很多离散小段，而不是一整段连续带
%   - max_bin_count < total_pixels：排除整帧单一码值这种退化情况
% 典型命中：
%   - gray step wedge
%   - Bayer dither
%   - 周期性人工 pattern
%   - 某些 concentric / spoke / hatch 类规则图
if bypass_flag == uint8(0)
    comb_ok = uint8(1);
    if int32(span_bin_count) < int32(cfg.pattern_comb_span_min)
        comb_ok = uint8(0);
    end
    if comb_ok == uint8(1)
        lhs_cb = int64(hole_count) * int64(cfg.pattern_comb_hole_denom);
        rhs_cb = int64(span_bin_count) * int64(cfg.pattern_comb_hole_numer);
        if lhs_cb < rhs_cb
            comb_ok = uint8(0);
        end
    end
    if int32(active_run_count) < int32(cfg.pattern_comb_runs_min)
        comb_ok = uint8(0);
    end
    if max_bin_count >= total_pixels
        comb_ok = uint8(0);
    end
    if comb_ok == uint8(1)
        bypass_flag = uint8(1);
        bypass_reason = 'comb';
    end
end

% ---------------------------------------------------------------
% 输出打包
% ---------------------------------------------------------------
% 输出不仅包含最终 bypass_flag，还把中间特征量一并导出。
% 这样做的作用是：
%   - 便于硬件 bring-up 时查看每帧到底命中了哪一类 pattern
%   - 便于后续根据误判样本重新调 pattern_* 寄存器阈值
%   - 便于把 bypass 结果和上层日志或离线分析脚本对接
result = struct();
result.bypass_flag = bypass_flag;
result.bypass_reason = bypass_reason;
result.active_bin_count = active_bin_count;
result.first_active_bin = first_active_bin;
result.last_active_bin = last_active_bin;
result.span_bin_count = span_bin_count;
result.hole_count = hole_count;
result.active_run_count = active_run_count;
result.max_bin_count = max_bin_count;
result.sum_abs_diff = sum_abs_diff;
result.sum_active_count = sum_active_count;
end
