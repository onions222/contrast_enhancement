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

% --- Pattern Bypass 寄存器 ---
% 这一组寄存器不参与主增强曲线的形状生成，而是作为前级保护层使用。
% 工作顺序是：
%   1. 先做 32-bin 粗直方图统计
%   2. 再依据这些 pattern_* 寄存器做 dense / sparse / comb 判定
%   3. 若命中，则本帧直接使用 identity LUT
% 因此这组寄存器的目的不是“增强更强”，而是“人工测试图更安全”。
%
% pattern_bypass_enable: 1 bit 寄存器，可调，1 = 开启 pattern bypass。
cfg.pattern_bypass_enable = uint8(1);
% pattern_hist_bin_count: U6.0，bypass 检测使用的 bin 数，固定 32。
cfg.pattern_hist_bin_count = uint8(32);
% Dense gradient 检测阈值。
% 这一路针对“bin 连续占满、起伏平缓”的规则分布。
% 常见命中对象：full ramp、near-black ramp、near-white ramp、部分规则渐变图。
cfg.pattern_dense_active_min = uint8(14);
cfg.pattern_dense_span_min = uint8(16);
cfg.pattern_dense_runs_max = uint8(2);
cfg.pattern_dense_holes_max = uint8(2);
% pattern_dense_flatness_numer / denom 组成 flatness 上限。
% 当前 3/4 表示：允许一定起伏，但不允许 histogram 相邻 bin 波动过大。
cfg.pattern_dense_flatness_numer = uint8(3);
cfg.pattern_dense_flatness_denom = uint8(4);
% Sparse pattern 检测阈值。
% 这一路针对“只落在少数几个灰阶桶”的规则图。
% 常见命中对象：SMPTE bars、gray step、color bars、少级数台阶图。
cfg.pattern_sparse_active_max = uint8(6);
% pattern_sparse_peak_numer / denom 用于限制单个 bin 的峰值占比。
% 当前 2/5 表示：若最大 bin 超过总像素 40%，则不走 sparse 分支。
% 这个限制用于避免把大面积单色自然场景都当作 sparse pattern。
cfg.pattern_sparse_peak_numer = uint8(2);
cfg.pattern_sparse_peak_denom = uint8(5);
% Comb pattern 检测阈值。
% 这一路针对“跨度大、空洞多、run 多”的梳状分布。
% 常见命中对象：Bayer-like 周期图、step wedge、某些网格/箱线 pattern。
cfg.pattern_comb_span_min = uint8(10);
cfg.pattern_comb_runs_min = uint8(6);
% pattern_comb_hole_numer / denom 组成 hole 比例下限。
% 当前 1/3 表示：在 first~last span 内，至少约三分之一位置为空洞才认为像 comb。
cfg.pattern_comb_hole_numer = uint8(1);
cfg.pattern_comb_hole_denom = uint8(3);

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
