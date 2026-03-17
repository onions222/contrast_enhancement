%RUN_CE_HW_BATCH 批量运行脚本入口。
% 说明：
%   - 这是运行外壳，不是核心硬件路径
%   - 本文件为可直接执行脚本，不再提供函数调用接口
%   - 用于批量组织 case、汇总 scene_name 和状态演化
%
% 输入变量：
%   - cases: cell，每个元素是 Nx3 或 Nx1 样本数组
%   - cfg: 配置 struct
%
% 输出变量：
%   - summary: 批量运行结果
%       * summary.cases      : 每个 case 的完整结果
%       * summary.scene_names: 场景字符串汇总
%       * summary.case_count : case 数量
%
% 用法示例：
%   - addpath('matlab');
%   - clear summary;
%   - run('matlab/run_ce_hw_batch.m');
%   - disp(summary.scene_names);

if ~exist('cfg', 'var') || isempty(cfg)
    cfg = ce_hw_config();
end
if ~exist('cases', 'var') || isempty(cases)
    % 默认批处理样本只用于 smoke test。
    cases = {
        int32([32 32 32; 64 48 32; 96 96 96]), ...
        int32([168 168 168; 168 168 168; 224 224 224]), ...
        int32([0 0 0; 8 8 8; 16 16 16]) ...
    };
end

summary = struct();
summary.cases = cell(1, numel(cases));
scene_names = cell(1, numel(cases));
prev_state = struct();
for idx = 1:numel(cases)
    input_frame = cases{idx};
    runtime = ce_hw_control_update(input_frame, cfg, prev_state);
    datapath = ce_hw_datapath(input_frame, runtime, cfg, 'rgb');

    result = struct();
    result.cfg = cfg;
    result.runtime = runtime;
    result.datapath = datapath;
    result.scene_id = runtime.scene_id;
    result.scene_name = runtime.scene_name;
    result.raw_scene_name = runtime.raw_scene_name;
    result.bypass_flag = runtime.bypass_flag;

    summary.cases{idx} = result;
    scene_names{idx} = result.scene_name;
    prev_state = result.runtime.state_out;
end
summary.scene_names = scene_names;
summary.case_count = numel(cases);
