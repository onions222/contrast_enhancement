function cfg = ce1_hw_config(varargin)
%CE1_HW_CONFIG 方案一 Percentile-Anchored PWL 的定点配置表。
% 设计目标：
%   - 提供可以直接映射到数字寄存器/ROM 的默认配置
%   - 所有比例类参数统一采用 Q8 编码
%   - 注释中显式写明位宽、寄存器属性和可调性

cfg = struct();

% cfg.name: 仅用于 MATLAB 运行显示，不参与硬件计算。
% 这不是硬件寄存器，只是为了在 MATLAB 侧区分当前配置属于哪条算法链路。
cfg.name = 'scheme1_percentile_pwl_hw';

% input_bit_depth: U4.0，配置寄存器，可调。
% 含义：
%   - 输入样本的原始位宽
%   - 控制路径和数据路径都会根据它决定如何把输入映射到 U8.0 域
% 作用：
%   - 大于 8bit 时右移
%   - 小于 8bit 时左移
cfg.input_bit_depth = uint8(8);
% input_max: U8.0，派生常量，不建议单独调。
% 含义：
%   - 当前实现里的目标最大码值
%   - 在 8bit 模式下固定对应 255
% 作用：
%   - 约束 LUT 输出范围
%   - 定义 PWL 终点坐标
cfg.input_max = uint16(255);
% lut_size: U9.0，常量 ROM 深度，不调。
% 含义：
%   - tone LUT 的表长
%   - 当前固定为 256 点，对应 8bit 全灰阶逐码查表
cfg.lut_size = uint16(256);
% n_bins: U6.0，粗直方图 bin 数，配置寄存器，通常固定为 32。
% 含义：
%   - 供输出摘要和 bypass 拓扑分析使用的粗直方图 bin 数
%   - 不参与 full 256-bin percentile anchor 搜索
cfg.n_bins = uint8(32);
% coarse_bin_shift: U4.0，32-bin 统计时的右移量，8bit 输入下固定为 3。
% 含义：
%   - 把 U8.0 灰度映射到 32-bin 的右移量
% 作用：
%   - input_u8 >> 3 后落到 0..31
cfg.coarse_bin_shift = uint8(3);

% frac_bits: U4.0，Q8 小数位宽，不调。
% 含义：
%   - 本算法所有比例类参数的小数位数
%   - 当前统一采用 Q8
cfg.frac_bits = uint8(8);
% frac_one: U9.0，对应 Q8 中的 1.0，不调。
% 含义：
%   - 定点表示中的“1.0”
%   - 256 即代表 1.0
cfg.frac_one = uint16(256);
% percent_den: U15.0，百分比 Q8 的分母 100 * 256 = 25600，不调。
% 含义：
%   - 百分位比较里的统一分母
% 作用：
%   - 使用 running_count * percent_den >= target_numer 的交叉比较
%   - 避免先做浮点或实数除法
cfg.percent_den = uint32(25600);

% gain_min_q8: U4.8，寄存器，可调，0.5 -> 128。
% 含义：
%   - 主增强段允许的最小斜率
% 作用：
%   - 防止输入动态范围很宽时，主段斜率过小，整条曲线过平
%   - 过小会导致增强失效，图像显得发灰
cfg.gain_min_q8 = uint16(128);
% gain_max_q8: U4.8，寄存器，可调，2.0 -> 512。
% 含义：
%   - 主增强段允许的最大斜率
% 作用：
%   - 防止输入动态范围较窄时，主段斜率过大
%   - 过大会把皮肤纹理、噪声、细小亮暗起伏一起放大
%   - 当前默认值恢复为更强增强，真正的皮肤保护交由 rgb_gain_blend 处理
cfg.gain_max_q8 = uint16(512);

% toe_margin: U8.0，寄存器，可调，默认 12。
% 含义：
%   - 输出端暗部预留的保护余量
%   - 即 y_low
% 作用：
%   - 让暗部不会被直接压到 0 附近
%   - 提供暗部保护段的起点，避免暗纹理/噪声被过度拉开
cfg.toe_margin = uint16(12);
% shoulder_margin: U8.0，寄存器，可调，默认 12。
% 含义：
%   - 输出端高光预留的保护余量
%   - 即 255 - y_high
% 作用：
%   - 让高光不会长期停在主增强段里被继续拉伸
%   - 对亮肤色、人脸额头反光、云层、白墙等高亮区域尤其重要
cfg.shoulder_margin = uint16(12);

% dark_percentile_q8: U7.8，寄存器，可调，2.0%% -> 512。
% 含义：
%   - 输入分布中暗端锚点的百分位
%   - 用于确定 p_low
% 作用：
%   - 忽略最暗少量异常像素
%   - 避免坏点、极少量黑边、孤立暗点把黑场锚点拉偏
cfg.dark_percentile_q8 = uint16(512);
% bright_percentile_q8: U7.8，寄存器，可调，98.0%% -> 25088。
% 含义：
%   - 输入分布中亮端锚点的百分位
%   - 用于确定 p_high
% 作用：
%   - 忽略最亮少量异常像素
%   - 避免孤立高光点、反射点、饱和小区域把白场锚点拉偏
cfg.bright_percentile_q8 = uint16(25088);

% alpha_num: U8.0，寄存器，可调，temporal IIR 分子。
% 含义：
%   - 帧间 LUT 平滑的“新值权重”
% 作用：
%   - 越大，当前帧 LUT 跟得越快
%   - 越小，输出更稳定，但响应更慢
cfg.alpha_num = uint16(1);
% alpha_den: U8.0，寄存器，可调，temporal IIR 分母。
% 含义：
%   - 帧间 LUT 平滑的总权重分母
% 作用：
%   - 与 alpha_num 一起决定 temporal IIR 强度
%   - 当前 1/8 表示“上一帧占 7/8，新帧占 1/8”
cfg.alpha_den = uint16(8);
% enable_temporal_smoothing: 1 bit 寄存器，可调。
% 含义：
%   - 是否启用帧间 LUT 平滑
% 作用：
%   - 1 时，当前帧 LUT 会和上一帧做 IIR 混合
%   - 0 时，每帧直接使用 raw LUT
cfg.enable_temporal_smoothing = uint8(1);

% rgb_gain_blend_q8: U1.8，寄存器，可调，0.25 -> 64。
% 含义：
%   - RGB 回写时，对 V 域 gain 的保守混合系数
% 公式：
%   - gain_blend = 1 + beta * (gain_raw - 1)
%   - 其中 beta = rgb_gain_blend_q8 / 256
% 作用：
%   - beta = 1 时，完整应用 V_out / V_in
%   - beta < 1 时，只部分应用亮度增益
%   - 这样可以减轻人脸皮肤、平滑高光区域出现的斑驳和块状感
cfg.rgb_gain_blend_q8 = uint16(64);

% identity_lut: 256 x U8.0，恒等 LUT ROM，运行时可直接复用。
% 含义：
%   - y = x 的恒等映射
% 作用：
%   - 第一帧初始化
%   - 空帧回退
%   - pattern bypass 命中时直接输出
cfg.identity_lut = uint16(0:255);

% --- Pattern Bypass 寄存器 ---
% 这一组寄存器不参与主增强曲线的形状生成，而是作为前级保护层使用。
% 工作顺序是：
%   1. 先做 32-bin 粗直方图统计
%   2. 再依据这些 pattern_* 寄存器做 topology bypass 判定
%   3. 若命中，则本帧直接使用 identity LUT
% 因此这组寄存器的目的不是“增强更强”，而是“人工测试图更安全”。
%
% pattern_bypass_enable: 1 bit 寄存器，可调，1 = 开启 pattern bypass。
% 含义：
%   - 是否在主增强前执行 topology bypass
% 作用：
%   - 保护 gray step、color bars、stripe 等人工测试图不被 CE 改坏
cfg.pattern_bypass_enable = uint8(1);
% pattern_hist_bin_count: U6.0，bypass 检测使用的 bin 数，固定 32。
% 含义：
%   - bypass 使用的粗直方图分辨率
% 作用：
%   - 只看拓扑连通性，不追求 full histogram 的精细灰度分辨率
cfg.pattern_hist_bin_count = uint8(32);
% pattern_active_threshold_shift: U4.0，活跃门限使用 TotalPixels >> shift。
% 含义：
%   - 判定某个粗直方图 bin 是否“活跃”的阈值位移
% 作用：
%   - TotalPixels >> shift 越大，越不容易把少量噪点当成活跃 bin
cfg.pattern_active_threshold_shift = uint8(10);
% Uniform / Sparse 判定阈值：A <= 2。
% 含义：
%   - 活跃 bin 数不超过这个值时，视为极简分布
% 典型命中：
%   - pure black / pure white / pure gray / 近纯色图
cfg.pattern_uniform_sparse_active_max = uint8(2);
% Narrow Continuous Transition 判定阈值：
% R == 1，且 A / F 都很小，同时 Pmax * 2 <= TotalPixels。
% 含义：
%   - 专门抓窄范围连续过渡，例如 near-black ramp / shallow ramp
% 这些图不是纯色，但也不应该进入常规 CE 主路径
cfg.pattern_narrow_continuous_active_max = uint8(8);
cfg.pattern_narrow_continuous_span_max = uint8(8);
cfg.pattern_narrow_continuous_peak_denom = uint8(2);
% Disconnected / Comb 判定阈值：R * 4 > A。
% 含义：
%   - 连续段数相对于活跃 bin 数过多，说明分布断断续续
% 典型命中：
%   - bars / comb / checker / stripe / step16
cfg.pattern_disconnected_comb_runs_mul = uint8(4);
% Continuous Artificial 判定阈值。
% 含义：
%   - 用于识别宽范围、单段连续、但又过于人工规则的 pattern
cfg.pattern_continuous_active_min = uint8(24);
cfg.pattern_continuous_span_min = uint8(24);
% max_bin_count * 16 <= TotalPixels。
% 含义：
%   - 单 bin 峰值不能太尖
%   - 若分布在宽范围内铺得很均匀，更像 ramp / gradient 类人工图
cfg.pattern_continuous_peak_denom = uint8(16);
% 连续宽分布主规则还要求 extrema_count 足够低。
% 含义：
%   - 活跃区内部不能有太多局部峰谷
%   - 过于平滑、过于规整的分布更偏人工 pattern
cfg.pattern_continuous_extrema_max = uint8(1);
% Special Continuous Artificial 后置补充分支阈值。
% 含义：
%   - 这是后置补刀分支，只在前面几条规则都没命中时再判断
%   - 目的不是重写主 bypass 逻辑，而是专门补特殊连续 pattern
cfg.pattern_special_continuous_active_min = uint8(24);
cfg.pattern_special_continuous_span_min = uint8(24);
cfg.pattern_special_continuous_peak_denom = uint8(12);
cfg.pattern_special_continuous_extrema_max = uint8(1);
% plateau/extrema/edge 这一组阈值主要服务特殊连续图的二级形态判断。
% 其中：
%   - plateau_diff_max 控制“相邻 bin 高度接近”的容忍度
%   - plateau_pair_min 要求有足够多的平坦相邻对
%   - edge_pair_max 要求高峰边缘对不能太多
% 用途：
%   - 把某些特殊连续人工图从普通自然连续分布里剥出来
cfg.pattern_special_plateau_extrema_max = uint8(3);
cfg.pattern_special_plateau_diff_max = uint16(256);
cfg.pattern_special_plateau_pair_min = uint8(28);
cfg.pattern_special_edge_pair_max = uint8(2);

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
