%RUN_CE1_HW_CASE 方案一单 case 直接运行脚本。
% 用法：
%   1. 直接运行本脚本，将使用默认 frame_in / cfg / prev_state
%   2. 若调用前 workspace 中已存在同名变量，则优先使用外部覆盖值
%
% 输出：
%   - result: 结构体，包含 cfg / frame_in / runtime / datapath

if ~exist('frame_in', 'var') || isempty(frame_in)
    frame_in = uint16([ ...
        16 24 32 48; ...
        64 80 96 112; ...
        128 144 160 176; ...
        192 208 224 240]);
end

if ~exist('cfg', 'var') || isempty(cfg)
    cfg = ce1_hw_config();
end

if ~exist('prev_state', 'var') || isempty(prev_state)
    prev_state = struct();
end

runtime = ce1_hw_control_update(frame_in, cfg, prev_state);
datapath = ce1_hw_datapath(frame_in, runtime, cfg);

result = struct();
result.cfg = cfg;
result.frame_in = frame_in;
result.runtime = runtime;
result.datapath = datapath;

disp('scheme1 single-case diagnostics');
disp(['pixels = ' num2str(double(runtime.total_pixels))]);
disp(['p_low = ' num2str(double(runtime.p_low)) ', p_high = ' num2str(double(runtime.p_high))]);
disp(['source_span = ' num2str(double(runtime.source_span))]);
disp(['gain_nominal_q8 = ' num2str(double(runtime.gain_nominal_q8))]);
disp(['gain_q8 = ' num2str(double(runtime.gain_q8))]);
disp(['anchor_low = ' num2str(double(runtime.anchor_low)) ', anchor_high = ' num2str(double(runtime.anchor_high))]);
disp(['lut0 = ' num2str(double(runtime.tone_lut(1))) ', lut255 = ' num2str(double(runtime.tone_lut(256)))]);
disp(['monotonic_ok = ' num2str(double(runtime.monotonic_ok))]);
disp('pwl_x =');
disp(double(runtime.pwl_x(:).'));
disp('pwl_y =');
disp(double(runtime.pwl_y(:).'));
