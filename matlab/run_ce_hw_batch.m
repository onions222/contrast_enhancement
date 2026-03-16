function summary = run_ce_hw_batch(cases, cfg)
%RUN_CE_HW_BATCH 批量运行入口。
% 说明：
%   - 这是运行外壳，不是核心硬件路径
%   - 用于批量组织 case、汇总 scene_name 和状态演化
%
% 输入参数：
%   - cases: cell，每个元素是 Nx3 或 Nx1 样本数组
%   - cfg: 配置 struct
%
% 输出参数：
%   - summary: 批量运行结果
%       * summary.cases      : 每个 case 的完整结果
%       * summary.scene_names: 场景字符串汇总
%       * summary.case_count : case 数量
%
% 备注：
%   - prev_state 在批处理中串联，用于观察 scene hold 行为
%   - 此函数偏验证/调试，不对应独立硬件单元

if nargin < 2 || isempty(cfg)
    cfg = ce_hw_config();
end
if nargin < 1 || isempty(cases)
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
    result = run_ce_hw_case(cases{idx}, cfg, prev_state, 'rgb');
    summary.cases{idx} = result;
    scene_names{idx} = result.scene_name;
    prev_state = result.runtime.state_out;
end
summary.scene_names = scene_names;
summary.case_count = numel(cases);
end
