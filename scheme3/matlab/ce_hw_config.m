function cfg = ce_hw_config(varargin)
%CE_HW_CONFIG 对比度增强 MATLAB 硬件运行时默认配置。
% 职责：
%   1. 提供配置寄存器/常量 ROM 的默认值
%   2. 固定关键 Q 格式、位宽、默认阈值和 curve family knot
%   3. 接收可选 override 结构体，覆盖默认配置
%
% 层级：
%   - Offline / Configuration Layer
%   - 不是逐像素数据路径，不做主输入遍历
%
% 输入参数：
%   - varargin{1}: 可选 struct，字段名与 cfg 字段一致
%     位宽语义：按字段本身定义，典型如 gain 上限为 U1.10 整数码值
%
% 输出参数：
%   - cfg: struct
%     关键字段位宽：
%       * cfg.input_bit_depth      : 标量控制量，推荐 4 bit 寄存
%       * cfg.input_max            : U8.0 或 U10.0 上限码值
%       * cfg.gain_one             : U1.10 中的 1.0，11 bit
%       * cfg.gain_max             : U1.10 最大值，11 bit
%       * cfg.family_*_knots       : knot 坐标表，MATLAB 中用 int32 保存
%
% rounding / saturation 规则：
%   - 本函数只定义参数，不执行 round / 饱和计算
%
% 与寄存器建议的关系：
%   - cfg 中多数标量字段可直接映射到 CE_CTRL_* / CE_GAIN_* 类寄存器
%   - cfg.family_*_knots 对应 curve 配置寄存器组

cfg = struct();
% 名称字段仅用于 MATLAB 运行外壳显示，不对应硬件计算位宽。
cfg.name = 'contrast_enhancement_hw_runtime';
% 输入位宽选择：8 或 10，建议映射到 1 bit 配置寄存器。
cfg.input_bit_depth = 8;
% 输入上限码值：U8.0 默认 255。
cfg.input_max = uint16(255);
% LUT 深度：256 点，建议用 9 bit 地址索引。
cfg.lut_size = 256;
% histogram bin 数：控制路径参数，当前 MATLAB 版本用于建模说明。
cfg.n_bins = 32;

% gain_frac_bits = 10，表示 gain 采用 U1.10。
cfg.gain_frac_bits = 10;
% gain_one = 2^10，对应 1.0 的 U1.10 码值，11 bit。
cfg.gain_one = bitshift(uint16(1), cfg.gain_frac_bits);
% gain_max = 1792，表示 1.75 的 U1.10 码值，11 bit。
cfg.gain_max = uint16(1792);

% 以下阈值可直接映射到 DDIC 控制寄存器。
% 默认值按当前图证与文献重构版本收敛：
%   - Bright 需要更高的平均亮度和高亮像素占比，避免“只是偏亮”就误判为亮场
%   - Dark II 要求更纯的低调分布；若仍带一定中灰细节，则优先归到 Dark I
cfg.bypass_dynamic_range_threshold = 4.0;
cfg.bright_mean_threshold = 176.0;
cfg.bright_ratio_threshold = 0.25;
cfg.dark2_mean_threshold = 48.0;
cfg.dark2_ratio_threshold = 0.85;
cfg.dark2_bright_ratio_threshold = 0.01;
cfg.dark1_mean_threshold = 96.0;
cfg.dark1_ratio_threshold = 0.55;
cfg.scene_cut_mean_delta = 32.0;
cfg.scene_switch_confirm_frames = 2;
cfg.scene_hold_enable = true;

% 四个 scene 的强度参数，建议寄存器侧采用 Q0.8 编码。
cfg.normal_strength = 0.50;
cfg.bright_strength = 0.65;
cfg.dark_i_strength = 0.70;
cfg.dark_ii_strength = 0.85;

% scene_id 编码：2 bit 即可表示。
cfg.SCENE_NORMAL = uint8(0);
cfg.SCENE_BRIGHT = uint8(1);
cfg.SCENE_DARK_I = uint8(2);
cfg.SCENE_DARK_II = uint8(3);

% curve family knot：
% 每行格式为 [x, y]，x/y 都在 U8.0 域，MATLAB 中用 int32 存储以简化运算。
% 设计说明：
%   - family_m_knots: 对应图中 Normal / Dark II 共用基础曲线
%   - family_b_knots: 按图中亮场参考线重构，强制经过 (192,192)，高光 shoulder 落在 192 之后
%   - family_d_knots: Dark I 根据文献与经验重构，侧重保黑同时提升中灰
cfg.family_m_knots = int32([0 0; 64 40; 128 128; 192 224; 255 255]);
cfg.family_b_knots = int32([0 0; 96 64; 192 192; 224 236; 255 255]);
cfg.family_d_knots = int32([0 0; 48 24; 96 144; 192 232; 255 255]);

% q_table 为说明性字段，用于文档与 debug，不要求映射到真实寄存器。
cfg.q_table = struct( ...
    'tone_lut', 'U8.0', ...
    'gain_lut', 'U1.10', ...
    'rgb_in', 'U8.0 or U10.0', ...
    'rgb_out', 'U8.0 or U10.0', ...
    'luma', 'U8.0');

if nargin >= 1 && isstruct(varargin{1})
    % override 主要用于 MATLAB 调参和 bring-up，字段覆盖不改变 API。
    override = varargin{1};
    fields = fieldnames(override);
    for idx = 1:numel(fields)
        cfg.(fields{idx}) = override.(fields{idx});
    end
end
end
