function runtime = ce_hw_control_update(frame_in, cfg, prev_state)
%CE_HW_CONTROL_UPDATE 帧级控制路径更新函数。
% 职责：
%   1. 将输入样本统一归一化到 Y_8 统计域
%   2. 计算 mean / dark_ratio / bright_ratio / dynamic_range
%   3. 执行 bypass 判定、scene 判决、scene hold / scene-cut 逻辑
%   4. 生成 tone_lut(U8.0) 和 gain_lut(U1.10)
%
% 层级：
%   - Control Path
%   - 对应帧级控制逻辑，不是逐像素核心 datapath
%
% 输入参数：
%   - frame_in: Nx1 或 Nx3 整数数组
%       * Nx1 时：视为亮度样本，U8.0 或 U10.0
%       * Nx3 时：视为 RGB 输入，单通道 U8.0 或 U10.0
%   - cfg: 配置 struct，关键位宽见 ce_hw_config
%   - prev_state: 上一帧状态 struct
%       * current_scene_id : 2 bit
%       * pending_scene_id : 2 bit
%       * pending_count    : 2~4 bit
%       * prev_mean        : 推荐 Q8.8 或浮点外壳
%
% 输出参数：
%   - runtime: struct
%       * luma_u8         : U8.0
%       * histogram       : 32-bin 计数数组
%       * raw_scene_id    : 2 bit
%       * scene_id        : 2 bit
%       * bypass_flag     : 1 bit
%       * tone_lut        : 256 x U8.0
%       * gain_lut        : 256 x U1.10
%       * state_out       : 下一帧寄存状态
%
% rounding / saturation 规则：
%   - tone_lut 量化使用 round
%   - gain_lut 在 helper 中执行 round + clip
%   - scene 判决本身只做阈值比较，不涉及饱和
%
% 与寄存器字段关系：
%   - scene_id / bypass_flag 可映射到 CE_STATUS_0
%   - tone_lut / gain_lut 可视为 control-path runtime RAM 输出

if nargin < 2 || isempty(cfg)
    cfg = ce_hw_config();
end
if nargin < 3 || isempty(prev_state)
    prev_state = struct();
end

if size(frame_in, 2) == 3
    % luma_u8: U8.0，scene 统计与 gain 索引统一域。
    luma_u8 = ce_hw_helpers('rgb_to_luma8', frame_in, cfg.input_bit_depth);
else
    luma_u8 = ce_hw_helpers('normalize_to_u8', frame_in(:), cfg.input_bit_depth);
end

% stats 为控制路径统计量：mean/dark_ratio/bright_ratio 目前保留浮点外壳。
stats = ce_hw_helpers('summarize_luma', luma_u8);
% bypass_flag: 1 bit 控制标志。
bypass_flag = stats.dynamic_range <= cfg.bypass_dynamic_range_threshold;
% raw_scene_id: 2 bit，未经过 temporal hold 的瞬时 scene 结果。
raw_scene_id = ce_hw_helpers('classify_scene', stats, cfg);

if ~isfield(prev_state, 'current_scene_id')
    % 第一帧时，current_scene_id / pending_scene_id 直接收敛到 raw scene。
    current_scene_id = raw_scene_id;
    pending_scene_id = raw_scene_id;
    pending_count = 0;
    prev_mean = stats.mean;
else
    current_scene_id = uint8(prev_state.current_scene_id);
    pending_scene_id = uint8(prev_state.pending_scene_id);
    pending_count = double(prev_state.pending_count);
    prev_mean = double(prev_state.prev_mean);

    % scene_cut: 当 mean 跳变超过阈值时立即切换 scene。
    scene_cut = abs(stats.mean - prev_mean) >= cfg.scene_cut_mean_delta;
    if (~cfg.scene_hold_enable) || scene_cut
        current_scene_id = raw_scene_id;
        pending_scene_id = raw_scene_id;
        pending_count = 0;
    elseif raw_scene_id == current_scene_id
        pending_scene_id = raw_scene_id;
        pending_count = 0;
    elseif raw_scene_id ~= pending_scene_id
        pending_scene_id = raw_scene_id;
        pending_count = 1;
    else
        pending_count = pending_count + 1;
        if pending_count >= cfg.scene_switch_confirm_frames
            current_scene_id = raw_scene_id;
            pending_count = 0;
        end
    end
    prev_mean = stats.mean;
end

% curve_*: MATLAB 中保留 double 外壳，但输出 tone_lut 时收敛到 U8.0。
curve_m = ce_hw_helpers('blend_identity_curve', ce_hw_helpers('pwl_curve', cfg.family_m_knots, cfg), cfg.normal_strength);
curve_b = ce_hw_helpers('blend_identity_curve', ce_hw_helpers('pwl_curve', cfg.family_b_knots, cfg), cfg.bright_strength);
curve_d = ce_hw_helpers('blend_identity_curve', ce_hw_helpers('pwl_curve', cfg.family_d_knots, cfg), cfg.dark_i_strength);
curve_dark2 = ce_hw_helpers('blend_identity_curve', ce_hw_helpers('pwl_curve', cfg.family_m_knots, cfg), cfg.dark_ii_strength);

if bypass_flag
    % bypass 模式：tone_lut = identity(U8.0)，gain_lut = unity(U1.10)。
    tone_lut = uint8(0:(cfg.lut_size - 1));
    gain_lut = ce_hw_helpers('identity_gain_lut', cfg);
    scene_id = current_scene_id;
else
    % scene_id: 2 bit，经过 temporal hold 后的激活 scene。
    scene_id = current_scene_id;
    switch uint8(scene_id)
        case cfg.SCENE_BRIGHT
            tone_lut = uint8(round(curve_b));
        case cfg.SCENE_DARK_I
            tone_lut = uint8(round(curve_d));
        case cfg.SCENE_DARK_II
            tone_lut = uint8(round(curve_dark2));
        otherwise
            tone_lut = uint8(round(curve_m));
    end
    % gain_lut: 256 x U1.10，供下一层 datapath 查表。
    gain_lut = ce_hw_helpers('tone_to_gain_u110', tone_lut, cfg);
end

runtime = struct();
runtime.luma_u8 = uint8(luma_u8(:));
% histogram: 32 bin 统计结果，位宽取决于像素总数；MATLAB 里用 double 数组承载。
runtime.histogram = histcounts(double(runtime.luma_u8), 0:8:256);
runtime.stats = stats;
runtime.bypass_flag = logical(bypass_flag);
runtime.raw_scene_id = uint8(raw_scene_id);
runtime.raw_scene_name = ce_hw_helpers('scene_name', raw_scene_id, cfg);
runtime.scene_id = uint8(scene_id);
runtime.scene_name = ce_hw_helpers('scene_name', scene_id, cfg);
runtime.tone_lut = uint8(tone_lut);
runtime.gain_lut = uint16(gain_lut);
% state_out: 下一帧需要锁存的状态寄存器集合。
runtime.state_out = struct( ...
    'current_scene_id', uint8(scene_id), ...
    'pending_scene_id', uint8(pending_scene_id), ...
    'pending_count', pending_count, ...
    'prev_mean', prev_mean);
end
