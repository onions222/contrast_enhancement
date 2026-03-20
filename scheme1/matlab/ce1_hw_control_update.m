function runtime = ce1_hw_control_update(frame_in, cfg, prev_state)
%CE1_HW_CONTROL_UPDATE 方案一控制路径的整数 MATLAB 实现。
% 约束：
%   - 核心路径只使用整数运算
%   - 不调用高层数值 built-in
%   - 不拆 helper，关键步骤全部顺序展开
% 接口约定：
%   - cfg 必须由上层显式提供
%   - prev_state 必须由上层显式提供
%   - prev_state 固定包含：
%       prev_lut_valid : U1.0
%       prev_lut       : 256 x U8.0

% rows / cols 直接对应图像行列计数器。
rows = size(frame_in, 1);
cols = size(frame_in, 2);
% total_pixels 是 frame-level 统计总像素数。
total_pixels = rows * cols;

% Stage 0: 读入上一帧状态。
% 目的：
%   - 为 temporal IIR 提供 prev_lut
%   - 在空帧时允许直接回退到上一帧 LUT
% 处理方式：
%   - 若 prev_state.prev_lut_valid = 0，则回退到 identity LUT

% prev_lut_valid: 1 bit 状态寄存器，来自上一帧。
prev_lut_valid = uint8(prev_state.prev_lut_valid);
% prev_lut: 256 x U8.0 状态寄存器，锁存上一帧 LUT。
prev_lut = uint16(prev_state.prev_lut(:));

% input_u8: N x U8.0，按行优先展开后的 value 序列。
input_u8 = zeros(total_pixels, 1, 'uint16');
% histogram256: 256 x Uceil(log2(Npix+1)).0，统计 RAM。
histogram256 = zeros(256, 1, 'uint32');
% histogram32: 32 x Uceil(log2(Npix+1)).0，粗粒度统计 RAM。
histogram32 = zeros(32, 1, 'uint32');

% Stage 1: 输入归一化和 histogram 构建。
% 目的：
%   - 把输入统一映射到 U8.0 统计域
%   - 同时构建 256-bin 精确 histogram 和 32-bin 粗 histogram
% 关键公式：
%   input_u8 = normalize_to_u8(raw_sample)
%   histogram256[input_u8] += 1
%   histogram32[input_u8 >> 3] += 1
pixel_index = 1;
row_index = 1;
while row_index <= rows
    % 外层循环对应 RTL 中的行地址计数。
    col_index = 1;
    while col_index <= cols
        % 内层循环对应 RTL 中的列地址计数。
        % raw_sample: S16.0，本轮输入样本。
        % 默认输入已经满足 unsigned 与位宽约束。
        raw_sample = int32(frame_in(row_index, col_index));

        % norm_sample: U8.0，归一化后的 value 样本。
        norm_sample = raw_sample;
        if cfg.input_bit_depth > 8
            % 高位宽输入通过右移收敛到 8bit 统计域。
            norm_sample = bitshift(norm_sample, -(int32(cfg.input_bit_depth) - 8));
        elseif cfg.input_bit_depth < 8
            % 低位宽输入通过左移扩展到 8bit 统计域。
            norm_sample = bitshift(norm_sample, 8 - int32(cfg.input_bit_depth));
        end

        % input_u8 按行优先顺序输出。
        input_u8(pixel_index) = uint16(norm_sample);
        % 精细 histogram 用于 percentile 搜索。
        histogram256(norm_sample + 1) = histogram256(norm_sample + 1) + uint32(1);
        % 粗 histogram 用于输出粗粒度分布，不参与 anchor 搜索。
        histogram32(bitshift(norm_sample, -int32(cfg.coarse_bin_shift)) + 1) = ...
            histogram32(bitshift(norm_sample, -int32(cfg.coarse_bin_shift)) + 1) + uint32(1);
        % pixel_index 以行优先顺序线性增长。
        pixel_index = pixel_index + 1;
        col_index = col_index + 1;
    end
    row_index = row_index + 1;
end

% Stage 1.5: Pattern Bypass 检测。
% 目的：
%   - 在 percentile 搜索之前，先判断当前帧是否更像“人工构造 pattern”
%   - 这类输入通常不是自然图像内容，而是工厂/OQC/bring-up 阶段使用的测试图
%   - 对这类输入继续做 Percentile-Anchored PWL，虽然数学上可行，但工程上不希望改动其码值关系
%   - 因此命中后直接走 identity LUT，保证输出 = 输入，避免 gray step、color bar、stripe 等 pattern 被误增强
% 处理方式：
%   - 使用 Stage 1 已经得到的 32-bin 粗直方图做快速判定
%   - 只在控制路径做一次帧级判断，不进入像素主路径
%   - 判定逻辑拆到 ce1_pattern_bypass，便于单独阅读和与硬件状态机对应
% 输出：
%   - pattern_bypass_flag = 1 时，当前帧不再进入 Stage 2~9 的增强控制计算
%   - bypass_result 中保留命中特征和命中原因，便于 bring-up 阶段回看
bypass_result = ce1_pattern_bypass(histogram32, uint32(total_pixels), cfg);
pattern_bypass_flag = bypass_result.bypass_flag;

if total_pixels <= 0
    % Stage 1b: 空帧回退。
    % 目的：
    %   - 防止控制路径在无有效统计时输出未定义 LUT
    % 处理方式：
    %   - 优先复用 prev_lut
    %   - 若 prev_lut 不存在，则输出 identity LUT
    tone_lut = prev_lut;
    if prev_lut_valid == 0
        % 第一帧空输入时，只能退回 identity LUT。
        tone_lut = uint16(cfg.identity_lut(:));
    end
    % 空帧路径仍然返回完整 runtime，保证控制路径输出完整。
    runtime = struct();
    runtime.input_u8 = uint16([]);
    runtime.histogram = uint32(histogram32(:));
    runtime.histogram256 = uint32(histogram256(:));
    runtime.total_pixels = uint32(0);
    runtime.p_low = uint16(0);
    runtime.p_high = uint16(0);
    runtime.source_span = uint16(255);
    runtime.y_low = uint16(0);
    runtime.y_high = uint16(255);
    runtime.y_span = uint16(255);
    runtime.gain_nominal_q8 = uint16(256);
    runtime.gain_q8 = uint16(256);
    runtime.anchor_low = uint16(0);
    runtime.anchor_high = uint16(255);
    runtime.required_span = uint16(255);
    runtime.pwl_x = uint16([0; 0; 255; 255]);
    runtime.pwl_y = uint16([0; 0; 255; 255]);
    runtime.raw_lut = uint16(tone_lut(:));
    runtime.tone_lut = uint16(tone_lut(:));
    runtime.monotonic_ok = uint8(1);
    runtime.state_out = struct('prev_lut_valid', uint8(1), 'prev_lut', uint16(tone_lut(:)));
    return;
end

% 若 pattern bypass 命中，跳过 Stage 2~9，直接使用恒等 LUT。
if pattern_bypass_flag == uint8(1)
    % bypass 路径的核心思想是：
    %   - 本帧不再根据 histogram 重新生成增强曲线
    %   - 直接把 tone_lut 设成 identity_lut
    %   - 这样数据路径做 y = LUT[x] 时，输出码值严格等于输入码值
    %
    % 这里仍然填充一组完整的运行时字段，而不是只给一个 bypass_flag：
    %   - 便于后续 datapath / 调试接口保持固定结构
    %   - 也便于把 bypass 帧和正常增强帧放到同一条日志链路里观察
    %
    % temporal IIR（Stage 10）仍然保留：
    %   - 如果上一帧是增强帧、当前帧突然命中 bypass，直接硬切到 identity LUT
    %     可能导致帧间跳变
    %   - 继续走 Stage 10 可以让 LUT 在时域上平滑回到 identity
    %   - 因此 bypass 只跳过“空间控制计算”，不跳过“时域收敛”
    p_low = uint16(0);
    p_high = uint16(255);
    source_span = uint16(255);
    y_low = uint16(cfg.toe_margin);
    y_high = uint16(cfg.input_max - cfg.shoulder_margin);
    y_span = uint16(y_high - y_low);
    gain_nominal_q8 = uint16(256);
    gain_q8 = uint16(256);
    anchor_low = uint16(0);
    anchor_high = uint16(255);
    required_span = uint16(255);
    pwl_x = uint16([0; 0; 255; 255]);
    pwl_y = uint16([0; 0; 255; 255]);
    raw_lut = uint16(cfg.identity_lut(:));
    % 跳转到 Stage 10 temporal IIR。
else

% Stage 2: 构造百分位比较目标。
% 目的：
%   - 由 total_pixels 和百分位寄存器生成 percentile 搜索条件
% 关键思想：
%   - 使用 running_count * percent_den >= target_numer 的交叉乘法判断
%   - 避免先除法带来的小样本退化
% percentile search 实际采用整数交叉比较。
% low_target_numer / high_target_numer 相当于“目标累计计数”的未约分分子。
low_target_numer = int64(total_pixels) * int64(cfg.dark_percentile_q8);
high_target_numer = int64(total_pixels) * int64(cfg.bright_percentile_q8);
% Stage 2: 累积扫描得到 p_low 和 p_high。
% 目的：
%   - 确定输入主体区间
% 公式：
%   p_low  = first level where CDF(level) reaches dark_percentile
%   p_high = first level where CDF(level) reaches bright_percentile
% p_low / p_high: U8.0，统计寄存器输出。
p_low = uint16(0);
p_high = uint16(255);
running_count = int64(0);
tail_count = int64(0);
found_low = uint8(0);
found_high = uint8(0);
if high_target_numer <= 0
    p_high = uint16(0);
    found_high = uint8(1);
end

level_index = 0;
while level_index <= 255
    % p_low 使用从暗到亮的前向 CDF 累加器。
    if found_low == 0
        running_count = running_count + int64(histogram256(level_index + 1));
        compare_left = running_count * int64(cfg.percent_den);
        if compare_left >= low_target_numer
            p_low = uint16(level_index);
            found_low = uint8(1);
        end
    end

    % p_high 使用从亮到暗的反向 tail 扫描。
    if found_high == 0
        reverse_level = 255 - level_index;
        tail_count = tail_count + int64(histogram256(reverse_level + 1));
        compare_before = (int64(total_pixels) - tail_count) * int64(cfg.percent_den);
        if compare_before < high_target_numer
            p_high = uint16(reverse_level);
            found_high = uint8(1);
        end
    end

    if found_low ~= 0 && found_high ~= 0
        break;
    end
    level_index = level_index + 1;
end

% Stage 3: 构造输出工作区间。
% 目的：
%   - 给暗部和高光预留 margin，避免映射过满
% 公式：
%   y_low = toe_margin
%   y_high = 255 - shoulder_margin
% y_low / y_high / y_span: U8.0，输出端锚点寄存器。
y_low = uint16(cfg.toe_margin);
y_high = uint16(cfg.input_max - cfg.shoulder_margin);
if y_high < y_low
    % 防止异常配置导致输出区间反转。
    y_high = y_low;
end
y_span = uint16(y_high - y_low);

% source_span: U8.0，输入端 percentile span。
if p_high >= p_low
    source_span = uint16(p_high - p_low);
else
    % 理论上不应出现，但仍做保护。
    source_span = uint16(0);
end
if source_span == 0
    % 防止后续除法分母为 0。
    source_span = uint16(1);
end

% Stage 4: 计算 nominal gain。
% 目的：
%   - 度量“将 source_span 映射到输出工作区间需要多大主段斜率”
% 公式：
%   gain_nominal_q8 = floor((y_span * 256) / source_span)
% 实现：
%   - 分子先左移 frac_bits 位，再直接做整数除法。
gain_nominal_q8 = uint16(idivide(bitshift(int64(y_span), int32(cfg.frac_bits)), int64(source_span), 'floor'));

% Stage 5: gain 限幅。
% 目的：
%   - 限制增强强度，避免过度放大窄动态范围输入
% gain_q8: U4.8，gain 限幅寄存器值。
gain_q8 = gain_nominal_q8;
if gain_q8 < cfg.gain_min_q8
    % 输入动态范围过宽时，避免主段斜率过小。
    gain_q8 = cfg.gain_min_q8;
end
if gain_q8 > cfg.gain_max_q8
    % 输入动态范围过窄时，避免主段斜率过大。
    gain_q8 = cfg.gain_max_q8;
end

% Stage 6: 计算最终 anchor span。
% 目的：
%   - 若 nominal gain 合法，直接沿用 p_low/p_high
%   - 若 nominal gain 越界，则反推 required_span，并围绕 percentile 中心扩展
% 公式：
%   required_span = ceil((y_span * 256) / gain_q8)
%   anchor_low = floor((p_low + p_high - required_span) / 2)
%   anchor_high = anchor_low + required_span
% required_span / anchor_low / anchor_high: U8.0，扩展或收缩后的 anchor 区间。
if gain_nominal_q8 >= cfg.gain_min_q8 && gain_nominal_q8 <= cfg.gain_max_q8
    % nominal gain 合法时，anchor 直接使用 percentile 锚点。
    required_span = source_span;
    anchor_low = p_low;
    anchor_high = p_high;
else
    % nominal gain 越界时，先按受限 gain 反推所需 span。
    required_span = uint16(idivide(bitshift(int64(y_span), int32(cfg.frac_bits)), int64(gain_q8), 'ceil'));
    if required_span == 0
        % 极端配置下仍确保 span 至少为 1。
        required_span = uint16(1);
    end
    if required_span > cfg.input_max
        % 不允许目标 span 超过 8bit 全域。
        required_span = cfg.input_max;
    end

    % center2 = p_low + p_high，使用双倍中心避免 0.5 中心点丢失。
    center2 = int32(p_low) + int32(p_high);
    anchor_low_signed = bitshift(center2 - int32(required_span), -1);
    anchor_high_signed = anchor_low_signed + int32(required_span);
    if anchor_low_signed < 0
        % 左端越界时，整体向右平移。
        anchor_high_signed = anchor_high_signed - anchor_low_signed;
        anchor_low_signed = int32(0);
    end
    if anchor_high_signed > 255
        % 右端越界时，整体向左平移。
        anchor_low_signed = anchor_low_signed - (anchor_high_signed - 255);
        anchor_high_signed = int32(255);
    end
    if anchor_low_signed < 0
        % 再做一次保护，防止双侧同时越界后的负数残留。
        anchor_low_signed = int32(0);
    end
    if anchor_high_signed < anchor_low_signed
        % 保底保证 anchor_high 不小于 anchor_low。
        anchor_high_signed = anchor_low_signed;
    end
    anchor_low = uint16(anchor_low_signed);
    anchor_high = uint16(anchor_high_signed);
end

% Stage 7: 构建 4 点 PWL。
% 目的：
%   - 把增强曲线压缩成硬件友好的 knot 表达
% 说明：
%   - x 坐标保持 U8.0
%   - 当前方案只保留 4 个 knot，不再保留中点
%   - 因为原来的中点只是两端平均值，本质上仍落在同一条直线上
%   - 所以删掉中点以后，曲线自由度不变，但寄存器表达更简单
% 三段直线分别表示：
%   - 段 0: (0, 0) -> (anchor_low, y_low)
%   - 段 1: (anchor_low, y_low) -> (anchor_high, y_high)
%   - 段 2: (anchor_high, y_high) -> (255, 255)
% 其中段 1 就是主增强段：
%   - 其斜率直接对应前面 gain / anchor 计算得到的主映射关系
% 4 点 PWL 控制点：U8.0，knot 可写寄存器/ROM。
x0 = uint16(0);
y0 = uint16(0);
x1 = anchor_low;
y1 = y_low;
x2 = anchor_high;
y2 = y_high;
x4 = uint16(255);
y4 = uint16(255);

pwl_x = uint16([x0; x1; x2; x4]);
pwl_y = uint16([y0; y1; y2; y4]);

% PWL y 内部使用 Q8。
% y*_q8 直接对应硬件里“坐标值 + 小数位”的内部表示。
% 这里不再需要中点的 .5 语义，因此每个 knot 都直接由整数 y 坐标左移得到。
y0_q8 = int64(y0) * int64(cfg.frac_one);
y1_q8 = int64(y1) * int64(cfg.frac_one);
y2_q8 = int64(y2) * int64(cfg.frac_one);
y4_q8 = int64(y4) * int64(cfg.frac_one);

% Stage 8: 展开 PWL 得到 raw_lut。
% 目的：
%   - 为每个 level 生成最终 tone 映射
% 实现方式：
%   - 逐个 level 判断它属于哪一段直线
%   - 在对应线段内部做一次线性插值
%   - 内部先在 Q8 域算分子，再做一次整数除法
%   - 最终对除法结果执行 round-to-even，得到 U8.0 LUT 码值
% 三段对应关系：
%   - level <= x1          -> 使用段 0
%   - x1 < level <= x2     -> 使用段 1，也就是主增强段
%   - level > x2           -> 使用段 2
% 公式：
%   y(level) = y0 + (y1 - y0) * (level - x0) / (x1 - x0)
% raw_lut: 256 x U8.0，未做 temporal 的 tone LUT。
raw_lut = zeros(256, 1, 'uint16');
level_index = 0;
while level_index <= 255
    % 根据当前 level 落点，选择所属的 PWL 段。
    if level_index <= int32(x1)
        seg_x0 = int32(x0);
        seg_y0_q8 = y0_q8;
        seg_x1 = int32(x1);
        seg_y1_q8 = y1_q8;
    elseif level_index <= int32(x2)
        seg_x0 = int32(x1);
        seg_y0_q8 = y1_q8;
        seg_x1 = int32(x2);
        seg_y1_q8 = y2_q8;
    else
        seg_x0 = int32(x2);
        seg_y0_q8 = y2_q8;
        seg_x1 = int32(x4);
        seg_y1_q8 = y4_q8;
    end

    % span 为当前线段的 x 宽度。
    % 在当前 4 点结构下，正常情况下每段都应满足 seg_x1 >= seg_x0。
    % 这里保留 span = 1 的处理，只是为了避免退化配置时出现除数为 0。
    span = seg_x1 - seg_x0;
    if span <= 0
        span = 1;
    end
    % dx 是 level 在当前线段中的相对位置。
    % 也就是当前输入码值距离该段左端点的水平偏移。
    dx = int32(level_index) - seg_x0;
    if dx < 0
        dx = 0;
    end
    % dy_q8 为当前线段的 y 增量，保留 Q8 精度。
    % 若当前段是主增强段，则 dy_q8 / span 就对应主段斜率。
    dy_q8 = seg_y1_q8 - seg_y0_q8;
    % 把 y = y0 + dy * dx / span 改写成统一分子形式。
    % 这样做的目的是把整条插值关系统一收敛成：
    %   一个分子 interp_numer
    %   一个分母 span * 256
    % 便于后续整数除法实现。
    interp_numer = seg_y0_q8 * int64(span) + dy_q8 * int64(dx);

    divisor_u = int64(span) * int64(cfg.frac_one);
    quotient_u = idivide(interp_numer, divisor_u, 'floor');
    remainder_u = interp_numer - quotient_u * divisor_u;
    % rounded_step 使用 banker rounding。
    % 目的不是“提升视觉效果”，而是保证定点化后没有系统性上偏或下偏。
    rounded_step = quotient_u;
    twice_remainder = remainder_u + remainder_u;
    if twice_remainder > divisor_u
        rounded_step = rounded_step + int64(1);
    elseif twice_remainder == divisor_u
        if bitand(rounded_step, int64(1)) ~= 0
            rounded_step = rounded_step + int64(1);
        end
    end
    value = int32(rounded_step);
    if value < 0
        % 额外保护，防止异常配置时出现负输出。
        value = int32(0);
    end
    if value > 255
        % LUT 输出始终限制在 U8.0。
        value = int32(255);
    end
    raw_lut(level_index + 1) = uint16(value);
    level_index = level_index + 1;
end

% Stage 9: 单调约束和端点保护。
% 目的：
%   - 保证 LUT 单调不减，不破坏灰阶次序
% 公式：
%   lut[i] = max(lut[i], lut[i-1])
% 单调约束。
raw_lut(1) = uint16(0);
raw_lut(256) = uint16(255);
prev_value = uint16(0);
level_index = 1;
while level_index <= 256
    % prefix max scan，强制 LUT 单调不减。
    current_value = raw_lut(level_index);
    if current_value < prev_value
        current_value = prev_value;
    end
    if current_value > 255
        current_value = uint16(255);
    end
    raw_lut(level_index) = current_value;
    prev_value = current_value;
    level_index = level_index + 1;
end

end  % end of if pattern_bypass_flag == 1 ... else ... end

% Stage 10: temporal IIR。
% 目的：
%   - 降低相邻帧 LUT 抖动
% 公式：
%   lut[i] = floor(((alpha_den - alpha_num) * prev_lut[i] + alpha_num * raw_lut[i]) / alpha_den)
% 实现：
%   - IIR 分子保持整数域
%   - 直接做整数除法得到当前 LUT 码值
tone_lut = uint16(raw_lut(:));
if cfg.enable_temporal_smoothing ~= 0 && prev_lut_valid ~= 0
    % 只有在显式使能且存在上一帧 LUT 时才执行 IIR。
    tone_lut = zeros(256, 1, 'uint16');
    level_index = 1;
    while level_index <= 256
        % IIR 分子保持整数域，不做任何浮点。
        iir_numer = int64(cfg.alpha_den - cfg.alpha_num) * int64(prev_lut(level_index)) + ...
            int64(cfg.alpha_num) * int64(raw_lut(level_index));
        tone_value = int32(idivide(iir_numer, int64(cfg.alpha_den), 'floor'));
        if level_index == 1
            if tone_value < 0
                tone_value = 0;
            end
        else
            % IIR 后再次做局部单调约束，避免时间滤波引入回退。
            if tone_value < int32(tone_lut(level_index - 1))
                tone_value = int32(tone_lut(level_index - 1));
            end
        end
        if tone_value > 255
            tone_value = 255;
        end
        tone_lut(level_index) = uint16(tone_value);
        level_index = level_index + 1;
    end
    tone_lut(1) = uint16(0);
    tone_lut(256) = uint16(255);
end

monotonic_ok = uint8(1);
level_index = 2;
while level_index <= 256
    % monotonic_ok 仅作状态标记，不改变 LUT。
    if tone_lut(level_index) < tone_lut(level_index - 1)
        monotonic_ok = uint8(0);
    end
    level_index = level_index + 1;
end

runtime = struct();
% input_u8 保留扁平 value 序列。
runtime.input_u8 = uint16(input_u8(:));
runtime.histogram = uint32(histogram32(:));
runtime.histogram256 = uint32(histogram256(:));
runtime.total_pixels = uint32(total_pixels);
runtime.p_low = p_low;
runtime.p_high = p_high;
runtime.source_span = source_span;
runtime.y_low = y_low;
runtime.y_high = y_high;
runtime.y_span = y_span;
runtime.gain_nominal_q8 = gain_nominal_q8;
runtime.gain_q8 = gain_q8;
runtime.anchor_low = anchor_low;
runtime.anchor_high = anchor_high;
runtime.required_span = required_span;
runtime.pwl_x = uint16(pwl_x(:));
runtime.pwl_y = uint16(pwl_y(:));
runtime.raw_lut = uint16(raw_lut(:));
runtime.tone_lut = uint16(tone_lut(:));
runtime.monotonic_ok = monotonic_ok;
% state_out 是下一帧唯一需要锁存的运行时状态。
runtime.state_out = struct('prev_lut_valid', uint8(1), 'prev_lut', uint16(tone_lut(:)));
runtime.pattern_bypass_flag = pattern_bypass_flag;
runtime.pattern_bypass_reason = bypass_result.bypass_reason;
runtime.pattern_features = bypass_result;
end
