function runtime = ce1_hw_control_update(frame_in, cfg, prev_state)
%CE1_HW_CONTROL_UPDATE 方案一控制路径的整数 MATLAB 实现。
% 约束：
%   - 核心路径只使用整数运算
%   - 不调用高层数值 built-in
%   - 不拆 helper，关键步骤全部顺序展开

if nargin < 2 || isempty(cfg)
    % 未显式传入配置时，加载默认寄存器镜像。
    cfg = ce1_hw_config();
end
if nargin < 3 || isempty(prev_state)
    % 第一帧或独立单帧运行时，上一帧状态为空。
    prev_state = struct();
end

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
%   - 若 prev_state 中不存在有效 prev_lut，则回退到 identity LUT

% prev_lut_valid: 1 bit 状态寄存器，来自上一帧。
prev_lut_valid = uint8(0);
% prev_lut: 256 x U8.0 状态寄存器，锁存上一帧 LUT。
prev_lut = uint16(cfg.identity_lut(:));
if isfield(prev_state, 'prev_lut_valid')
    % 上一帧是否已经生成过有效 LUT。
    prev_lut_valid = uint8(prev_state.prev_lut_valid);
end
if isfield(prev_state, 'prev_lut') && numel(prev_state.prev_lut) == 256
    % 若存在上一帧 LUT，则覆盖 identity 缺省值。
    prev_lut = uint16(prev_state.prev_lut(:));
    prev_lut_valid = uint8(1);
end

% input_u8: N x U8.0，按行优先展开后的亮度序列。
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

        % norm_sample: U8.0，归一化后的亮度样本。
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
    runtime.pwl_x = uint16([0; 0; 128; 255; 255]);
    runtime.pwl_y = uint16([0; 0; 128; 255; 255]);
    runtime.raw_lut = uint16(tone_lut(:));
    runtime.tone_lut = uint16(tone_lut(:));
    runtime.monotonic_ok = uint8(1);
    runtime.state_out = struct('prev_lut_valid', uint8(1), 'prev_lut', uint16(tone_lut(:)));
    return;
end

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

% Stage 7: 构建 5 点 PWL。
% 目的：
%   - 把增强曲线压缩成硬件友好的 knot 表达
% 说明：
%   - x 坐标保持 U8.0
%   - y 坐标内部保留 Q8，以保留中间 knot 的 0.5 语义
% 5 点 PWL 控制点：U8.0，knot 可写寄存器/ROM。
x0 = uint16(0);
y0 = uint16(0);
x1 = anchor_low;
y1 = y_low;
x3 = anchor_high;
y3 = y_high;
% 中点 x 使用 round-to-even。
sum_mid = int32(x1) + int32(x3);
mid_x_signed = bitshift(sum_mid, -1);
if bitand(sum_mid, int32(1)) ~= 0 && bitand(mid_x_signed, int32(1)) ~= 0
    mid_x_signed = mid_x_signed + int32(1);
end
mid_x = uint16(mid_x_signed);

% 中点 y 在内部保留 Q8 精度，因此这里先保留整数部分定义。
sum_mid = int32(y1) + int32(y3);
mid_y_signed = bitshift(sum_mid, -1);
if bitand(sum_mid, int32(1)) ~= 0 && bitand(mid_y_signed, int32(1)) ~= 0
    mid_y_signed = mid_y_signed + int32(1);
end
mid_y = uint16(mid_y_signed);
x4 = uint16(255);
y4 = uint16(255);

pwl_x = uint16([x0; x1; mid_x; x3; x4]);
pwl_y = uint16([y0; y1; mid_y; y3; y4]);

% PWL y 内部使用 Q8，以保留中间 knot 的 0.5 语义。
% y*_q8 直接对应硬件里“坐标值 + 小数位”的内部表示。
y0_q8 = int64(y0) * int64(cfg.frac_one);
y1_q8 = int64(y1) * int64(cfg.frac_one);
mid_y_q8 = int64(int32(y1) + int32(y3)) * int64(bitshift(int32(1), int32(cfg.frac_bits - 1)));
y3_q8 = int64(y3) * int64(cfg.frac_one);
y4_q8 = int64(y4) * int64(cfg.frac_one);

% Stage 8: 展开 PWL 得到 raw_lut。
% 目的：
%   - 为每个 level 生成最终 tone 映射
% 公式：
%   y(level) = y0 + (y1 - y0) * (level - x0) / (x1 - x0)
% 实现方式：
%   - 内部在 Q8 域插值
%   - 先做整数除法，再对余数执行 round-to-even
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
    elseif level_index <= int32(mid_x)
        seg_x0 = int32(x1);
        seg_y0_q8 = y1_q8;
        seg_x1 = int32(mid_x);
        seg_y1_q8 = mid_y_q8;
    elseif level_index <= int32(x3)
        seg_x0 = int32(mid_x);
        seg_y0_q8 = mid_y_q8;
        seg_x1 = int32(x3);
        seg_y1_q8 = y3_q8;
    else
        seg_x0 = int32(x3);
        seg_y0_q8 = y3_q8;
        seg_x1 = int32(x4);
        seg_y1_q8 = y4_q8;
    end

    % span 为当前线段的 x 宽度，至少强制为 1。
    span = seg_x1 - seg_x0;
    if span <= 0
        span = 1;
    end
    % dx 是 level 在当前线段中的相对位置。
    dx = int32(level_index) - seg_x0;
    if dx < 0
        dx = 0;
    end
    % dy_q8 为当前线段的 y 增量，保留 Q8 精度。
    dy_q8 = seg_y1_q8 - seg_y0_q8;
    % 把 y = y0 + dy * dx / span 改写成统一分子形式。
    interp_numer = seg_y0_q8 * int64(span) + dy_q8 * int64(dx);

    divisor_u = int64(span) * int64(cfg.frac_one);
    quotient_u = idivide(interp_numer, divisor_u, 'floor');
    remainder_u = interp_numer - quotient_u * divisor_u;
    % rounded_step 使用 banker rounding。
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
% input_u8 保留扁平亮度序列。
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
end
