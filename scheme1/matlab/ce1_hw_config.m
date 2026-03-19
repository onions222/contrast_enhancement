function cfg = ce1_hw_config(varargin)
%CE1_HW_CONFIG 方案一 Percentile-Anchored PWL 的定点配置表。
% 设计目标：
%   - 提供可以直接映射到数字寄存器/ROM 的默认配置
%   - 所有比例类参数统一采用 Q8 编码
%   - 注释中显式写明位宽、寄存器属性和可调性

cfg = struct();

% cfg.name: 仅用于 MATLAB 运行显示，不参与硬件计算。
cfg.name = 'scheme1_percentile_pwl_hw';

% input_bit_depth: U4.0，配置寄存器，可调。
cfg.input_bit_depth = uint8(8);
% input_max: U8.0，派生常量，不建议单独调。
cfg.input_max = uint16(255);
% lut_size: U9.0，常量 ROM 深度，不调。
cfg.lut_size = uint16(256);
% n_bins: U6.0，粗直方图 bin 数，配置寄存器，通常固定为 32。
cfg.n_bins = uint8(32);
% coarse_bin_shift: U4.0，32-bin 统计时的右移量，8bit 输入下固定为 3。
cfg.coarse_bin_shift = uint8(3);

% frac_bits: U4.0，Q8 小数位宽，不调。
cfg.frac_bits = uint8(8);
% frac_one: U9.0，对应 Q8 中的 1.0，不调。
cfg.frac_one = uint16(256);
% percent_den: U15.0，百分比 Q8 的分母 100 * 256 = 25600，不调。
cfg.percent_den = uint32(25600);

% gain_min_q8: U4.8，寄存器，可调，0.5 -> 128。
cfg.gain_min_q8 = uint16(128);
% gain_max_q8: U4.8，寄存器，可调，2.0 -> 512。
cfg.gain_max_q8 = uint16(512);

% toe_margin: U8.0，寄存器，可调，默认 12。
cfg.toe_margin = uint16(12);
% shoulder_margin: U8.0，寄存器，可调，默认 12。
cfg.shoulder_margin = uint16(12);

% dark_percentile_q8: U7.8，寄存器，可调，2.0%% -> 512。
cfg.dark_percentile_q8 = uint16(512);
% bright_percentile_q8: U7.8，寄存器，可调，98.0%% -> 25088。
cfg.bright_percentile_q8 = uint16(25088);

% alpha_num: U8.0，寄存器，可调，temporal IIR 分子。
cfg.alpha_num = uint16(1);
% alpha_den: U8.0，寄存器，可调，temporal IIR 分母。
cfg.alpha_den = uint16(8);
% enable_temporal_smoothing: 1 bit 寄存器，可调。
cfg.enable_temporal_smoothing = uint8(1);

% identity_lut: 256 x U8.0，恒等 LUT ROM，运行时可直接复用。
cfg.identity_lut = uint16(0:255);

if nargin >= 1 && isstruct(varargin{1})
    override = varargin{1};
    fields = fieldnames(override);
    field_count = numel(fields);
    field_index = 1;
    while field_index <= field_count
        cfg.(fields{field_index}) = override.(fields{field_index});
        field_index = field_index + 1;
    end
end
end
