function out = ce_hw_datapath(input_frame, runtime, cfg, mode)
%CE_HW_DATAPATH 像素级数据路径仿真函数。
% 职责：
%   1. 将输入样本转换到 LUT 索引域 V_8
%   2. 从 runtime.gain_lut 中查出每像素 gain_samples_code
%   3. 根据 mode 选择输出 gain-only 或执行 gain x RGB
%   4. 对乘法结果执行 round 和饱和
%
% 层级：
%   - Datapath
%   - 这是核心硬件路径的 MATLAB 表达
%
% 输入参数：
%   - input_frame: Nx1 或 Nx3 整数样本
%       * Nx3 时通道位宽为 U8.0 或 U10.0
%   - runtime.gain_lut: 256 x U1.10
%   - cfg: 配置 struct，包含 gain_frac_bits、input_bit_depth 等
%   - mode: 'gain' 或 'rgb'
%
% 输出参数：
%   - out.value_u8           : U8.0
%   - out.gain_samples_code  : U1.10
%   - out.gain_samples_f     : 调试用浮点外壳
%   - out.gain_out           : U1.10
%   - out.rgb_out            : U8.0 / U10.0，经 round + 饱和后的输出
%
% rounding / saturation 规则：
%   - gain x RGB 之后统一加 2^(F-1) 再右移 F 位
%   - 最终输出 clip 到合法 unsigned 范围，不使用 wrap
%
% 与文档公式关系：
%   - 对应 T_s(y) -> G(i) -> gain_out / RGB 乘法 的最终数据路径

if nargin < 3 || isempty(cfg)
    cfg = ce_hw_config();
end
if nargin < 4 || isempty(mode)
    mode = 'rgb';
end

if size(input_frame, 2) == 3
    % rgb_in: 原始输入码值，推荐 U8.0/U10.0，MATLAB 中使用 int32 便于后续乘法。
    rgb_in = int32(input_frame);
    value_u8 = ce_hw_helpers('rgb_to_value8', rgb_in, cfg.input_bit_depth);
else
    rgb_in = [];
    value_u8 = ce_hw_helpers('normalize_to_u8', input_frame(:), cfg.input_bit_depth);
end

% indices: LUT 地址，取值范围 1..256，对应硬件中的 8 bit 索引 + MATLAB 1-based 偏移。
indices = double(value_u8(:)) + 1;
% gain_samples_code: U1.10，每像素查表得到的 gain 码值。
gain_samples_code = double(runtime.gain_lut(indices));
% gain_samples_f: 仅用于 debug / 可视化，不属于核心硬件路径。
gain_samples_f = gain_samples_code / double(cfg.gain_one);

out = struct();
out.value_u8 = uint8(value_u8(:));
out.gain_samples_code = uint16(gain_samples_code);
out.gain_samples_f = gain_samples_f;
out.gain_mode_enabled = strcmpi(mode, 'gain');
out.gain_out = uint16(gain_samples_code);

if out.gain_mode_enabled || isempty(rgb_in)
    % gain-only 模式下只输出 gain_out，不做 RGB 乘法。
    out.rgb_out = [];
    out.tone_out = uint8(runtime.tone_lut(indices));
    return;
end

% output_max: 合法输出码值上限，U8.0 或 U10.0。
output_max = int32(2^double(cfg.input_bit_depth) - 1);
% mult_codes: 乘法回缩前中间量，位宽通常为 19~21 bit。
mult_codes = int64(rgb_in) .* int64(reshape(gain_samples_code, [], 1));
% rgb_scaled: round_shift_right 后的中间结果，再进入饱和器。
rgb_scaled = ce_hw_helpers('round_shift_right', mult_codes, cfg.gain_frac_bits);
rgb_scaled = ce_hw_helpers('saturate_unsigned', rgb_scaled, output_max);
out.rgb_out = int32(rgb_scaled);
out.tone_out = uint8(runtime.tone_lut(indices));
end
