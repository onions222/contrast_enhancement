function varargout = ce_hw_helpers(action, varargin)
%CE_HW_HELPERS 手工定点语义辅助函数集合。
% 职责：
%   - 统一封装位宽归一化、Q 格式变换、round、饱和和 scene 判决
%   - 为 control path / datapath 提供可复用的 MATLAB 建模辅助
%
% 层级：
%   - 建模辅助层
%   - 不是独立硬件模块；真实硬件会把这些 helper 分散映射到控制或数据路径
%
% 输入参数：
%   - action: helper 名称字符串
%   - varargin: 对应 helper 的参数
%
% 输出参数：
%   - varargout: helper 返回值
%
% 关键规则：
%   - 涉及 U1.10 的地方显式标注 Q 格式
%   - 乘法回缩统一使用 round-to-nearest
%   - 饱和统一 clip，不使用 wrap

switch action
    case 'clip_to_bit_depth'
        varargout{1} = local_clip_to_bit_depth(varargin{1}, varargin{2});
    case 'normalize_to_u8'
        varargout{1} = local_normalize_to_u8(varargin{1}, varargin{2});
    case 'rgb_to_luma8'
        varargout{1} = local_rgb_to_luma8(varargin{1}, varargin{2});
    case 'summarize_luma'
        varargout{1} = local_summarize_luma(varargin{1});
    case 'pwl_curve'
        varargout{1} = local_pwl_curve(varargin{1}, varargin{2});
    case 'blend_identity_curve'
        varargout{1} = local_blend_identity_curve(varargin{1}, varargin{2});
    case 'tone_to_gain_u110'
        varargout{1} = local_tone_to_gain_u110(varargin{1}, varargin{2});
    case 'identity_gain_lut'
        varargout{1} = [uint16(0), repmat(varargin{1}.gain_one, 1, varargin{1}.lut_size - 1)];
    case 'classify_scene'
        varargout{1} = local_classify_scene(varargin{1}, varargin{2});
    case 'scene_name'
        varargout{1} = local_scene_name(varargin{1}, varargin{2});
    case 'round_shift_right'
        varargout{1} = local_round_shift_right(varargin{1}, varargin{2});
    case 'saturate_unsigned'
        varargout{1} = local_saturate_unsigned(varargin{1}, varargin{2});
    otherwise
        error('ce_hw_helpers:UnknownAction', 'Unknown action: %s', action);
end
end

function out = local_clip_to_bit_depth(values, bit_depth)
%LOCAL_CLIP_TO_BIT_DEPTH 将输入裁剪到目标位宽合法范围。
% 输入 values 可视为有符号中间量；输出范围为 [0, 2^bit_depth-1]。
max_value = int32(2^double(bit_depth) - 1);
values_i32 = int32(values);
out = min(max(values_i32, 0), max_value);
end

function out = local_normalize_to_u8(values, bit_depth)
%LOCAL_NORMALIZE_TO_U8 将 U8.0/U10.0 等输入统一归一化到 U8.0。
% bit_depth > 8 时右移；bit_depth < 8 时左移；都先执行合法范围裁剪。
clipped = local_clip_to_bit_depth(values, bit_depth);
if bit_depth == 8
    out = uint8(clipped);
elseif bit_depth > 8
    out = uint8(bitshift(clipped, -(bit_depth - 8)));
else
    out = uint8(min(bitshift(clipped, 8 - bit_depth), 255));
end
end

function y8 = local_rgb_to_luma8(rgb, bit_depth)
%LOCAL_RGB_TO_LUMA8 计算 Y_8 = (77R + 150G + 29B + 128) / 256。
% 输入 rgb 通道视为 U8.0/U10.0；输出 y8 为 U8.0。
rgb_i32 = int32(rgb);
r = int32(local_normalize_to_u8(rgb_i32(:, 1), bit_depth));
g = int32(local_normalize_to_u8(rgb_i32(:, 2), bit_depth));
b = int32(local_normalize_to_u8(rgb_i32(:, 3), bit_depth));
y8 = uint8(min(idivide(77 .* r + 150 .* g + 29 .* b + 128, int32(256), 'floor'), 255));
end

function stats = local_summarize_luma(luma)
%LOCAL_SUMMARIZE_LUMA 计算 frame 级统计量。
% luma 输入为 U8.0；输出 stats 中 mean/ratio 保留浮点外壳用于控制路径判决。
luma_i32 = int32(luma(:));
if isempty(luma_i32)
    stats = struct('mean', 0.0, 'dark_ratio', 0.0, 'bright_ratio', 0.0, ...
        'p2', 0.0, 'p98', 0.0, 'dynamic_range', 0.0, 'min_luma', 0.0, 'max_luma', 0.0);
    return;
end

sorted = sort(double(luma_i32));
total = double(numel(sorted));
stats = struct();
stats.mean = mean(sorted);
stats.dark_ratio = sum(sorted <= 63) / total;
stats.bright_ratio = sum(sorted >= 192) / total;
stats.p2 = local_percentile(sorted, 2.0);
stats.p98 = local_percentile(sorted, 98.0);
stats.dynamic_range = stats.p98 - stats.p2;
stats.min_luma = sorted(1);
stats.max_luma = sorted(end);
end

function p = local_percentile(sorted_values, percentile)
%LOCAL_PERCENTILE 百分位计算 helper。
% 这是 MATLAB 验证/控制外壳函数，不要求映射为实时硬件单元。
if isempty(sorted_values)
    p = 0.0;
    return;
end
if numel(sorted_values) == 1
    p = sorted_values(1);
    return;
end
rank = (numel(sorted_values) - 1) * percentile / 100.0;
lower = floor(rank) + 1;
upper = min(lower + 1, numel(sorted_values));
blend = rank - floor(rank);
p = sorted_values(lower) + blend * (sorted_values(upper) - sorted_values(lower));
end

function curve = local_pwl_curve(knots, cfg)
%LOCAL_PWL_CURVE 根据 knot 表生成 PWL curve。
% knot 的 x/y 都在 U8.0 域；curve 输出在 MATLAB 中保留 double 外壳，再裁剪回 [0,255]。
curve = zeros(1, cfg.lut_size, 'double');
points = double(knots);
for level = 0:(cfg.lut_size - 1)
    if level <= points(1, 1)
        curve(level + 1) = points(1, 2);
    elseif level >= points(end, 1)
        curve(level + 1) = points(end, 2);
    else
        for idx = 1:(size(points, 1) - 1)
            x0 = points(idx, 1);
            y0 = points(idx, 2);
            x1 = points(idx + 1, 1);
            y1 = points(idx + 1, 2);
            if level >= x0 && level <= x1
                span = max(x1 - x0, 1);
                curve(level + 1) = y0 + (y1 - y0) * (level - x0) / span;
                break;
            end
        end
    end
end
curve = max(min(curve, double(cfg.input_max)), 0.0);
curve = local_monotonic_curve(curve);
end

function curve = local_blend_identity_curve(curve_in, strength)
%LOCAL_BLEND_IDENTITY_CURVE 按 scene 强度将 PWL curve 与 identity 混合。
% strength 建议寄存器侧用 Q0.8；MATLAB 中当前保留 double 外壳。
curve = zeros(size(curve_in), 'double');
blend = max(0.0, min(1.0, double(strength)));
for idx = 1:numel(curve_in)
    curve(idx) = (1.0 - blend) * double(idx - 1) + blend * double(curve_in(idx));
end
curve = local_monotonic_curve(curve);
end

function gain_lut = local_tone_to_gain_u110(tone_lut, cfg)
%LOCAL_TONE_TO_GAIN_U110 将 U8.0 tone LUT 转成 U1.10 gain LUT。
% rounding: 使用 round；饱和: clip 到 cfg.gain_max。
gain_lut = zeros(1, cfg.lut_size, 'uint16');
gain_lut(1) = uint16(0);
for level = 1:(cfg.lut_size - 1)
    numerator = double(tone_lut(level + 1)) * double(cfg.gain_one);
    gain = round(numerator / double(level));
gain_lut(level + 1) = uint16(min(max(gain, 0), double(cfg.gain_max)));
end
end

function scene_id = local_classify_scene(stats, cfg)
%LOCAL_CLASSIFY_SCENE 根据 mean / dark_ratio / bright_ratio 判定 scene_id。
% 输出 scene_id 为 2 bit 控制量。
if stats.mean >= cfg.bright_mean_threshold && stats.bright_ratio >= cfg.bright_ratio_threshold
    scene_id = cfg.SCENE_BRIGHT;
elseif stats.mean <= cfg.dark2_mean_threshold && stats.dark_ratio >= cfg.dark2_ratio_threshold ...
        && stats.bright_ratio <= cfg.dark2_bright_ratio_threshold
    scene_id = cfg.SCENE_DARK_II;
elseif stats.mean <= cfg.dark1_mean_threshold && stats.dark_ratio >= cfg.dark1_ratio_threshold
    scene_id = cfg.SCENE_DARK_I;
else
    scene_id = cfg.SCENE_NORMAL;
end
end

function name = local_scene_name(scene_id, cfg)
%LOCAL_SCENE_NAME 将 2 bit scene_id 转换为 debug 字符串。
switch uint8(scene_id)
    case cfg.SCENE_NORMAL
        name = 'Normal';
    case cfg.SCENE_BRIGHT
        name = 'Bright';
    case cfg.SCENE_DARK_I
        name = 'Dark I';
    case cfg.SCENE_DARK_II
        name = 'Dark II';
    otherwise
        name = 'Unknown';
end
end

function out = local_round_shift_right(values, shift)
%LOCAL_ROUND_SHIFT_RIGHT 对乘法结果执行 round-to-nearest 后右移。
% values 常见来源为 mult_codes，位宽约 19~21 bit；shift 对应 gain_frac_bits。
values_i64 = int64(values);
if shift <= 0
    out = values_i64;
    return;
end
bias = bitshift(int64(1), shift - 1);
out = bitshift(values_i64 + bias, -shift);
end

function out = local_saturate_unsigned(values, max_value)
%LOCAL_SATURATE_UNSIGNED 执行 unsigned 饱和裁剪。
% 饱和输出位宽由 max_value 对应的 U8.0/U10.0 决定。
out = min(max(int64(values), 0), int64(max_value));
end

function curve = local_monotonic_curve(curve_in)
%LOCAL_MONOTONIC_CURVE 对 curve 做单调非降修正。
% 输出仍保持在 MATLAB double 外壳，用于后续量化到 U8.0。
curve = curve_in;
prev = curve(1);
for idx = 2:numel(curve)
    prev = max(prev, curve(idx));
    curve(idx) = prev;
end
end
