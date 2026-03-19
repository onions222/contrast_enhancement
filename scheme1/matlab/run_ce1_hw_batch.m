%RUN_CE1_HW_BATCH 方案一 batch 直接运行脚本。
% 用法：
%   1. 直接运行本脚本，将使用默认 cases 和 cfg
%   2. 若调用前 workspace 中已存在 cases / cfg，则优先使用外部覆盖值
%
% 输出：
%   - summary: 结构体，包含 case_count 和逐 case 结果

if ~exist('cfg', 'var') || isempty(cfg)
    cfg = ce1_hw_config();
end

if ~exist('cases', 'var') || isempty(cases)
    cases = cell(4, 1);
    cases{1} = {uint16([])};
    cases{2} = {uint16([32 32 96 96 160 160 160 224])};
    cases{3} = {uint16([120 120 120 122 122 122 124 124 124])};
    cases{4} = {
        uint16([32 32 32 128 128 128 196 196 196]), ...
        uint16([40 40 40 136 136 136 204 204 204])};
end

summary = struct();
summary.case_count = uint32(numel(cases));
summary.results = cell(numel(cases), 1);

case_index = 1;
while case_index <= numel(cases)
    frames = cases{case_index};
    state = struct();
    frame_results = cell(numel(frames), 1);
    frame_index = 1;
    while frame_index <= numel(frames)
        runtime = ce1_hw_control_update(frames{frame_index}, cfg, state);
        datapath = ce1_hw_datapath(frames{frame_index}, runtime, cfg);
        frame_results{frame_index} = struct('runtime', runtime, 'datapath', datapath);
        state = runtime.state_out;
        frame_index = frame_index + 1;
    end
    summary.results{case_index} = frame_results;
    case_index = case_index + 1;
end

disp(['scheme1 batch cases = ' num2str(double(summary.case_count))]);
