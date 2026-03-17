%RUN_CE_HW_CASE 单 case 脚本入口。
% 说明：
%   - 这是运行外壳，不是核心硬件路径
%   - 本文件为可直接执行脚本，不再提供函数调用接口
%   - 它负责串联 control_update 和 datapath，便于单例调试
%
% 输入变量：
%   - input_frame: Nx3 或 Nx1 样本，通道位宽 U8.0/U10.0
%   - cfg: 配置 struct
%   - prev_state: 上一帧状态寄存器集合
%   - mode: 'rgb' 或 'gain'
%
% 输出变量：
%   - result: 结果 struct
%       * scene_id / bypass_flag 为控制结果
%       * runtime / datapath 为完整调试输出
%
% 用法示例：
%   - addpath('matlab');
%   - clear result;
%   - run('matlab/run_ce_hw_case.m');
%   - disp(result.scene_name);

if ~exist('cfg', 'var') || isempty(cfg)
    cfg = ce_hw_config();
end
if ~exist('prev_state', 'var') || isempty(prev_state)
    prev_state = struct();
end
if ~exist('mode', 'var') || isempty(mode)
    mode = 'rgb';
end
if ~exist('input_frame', 'var') || isempty(input_frame)
    % 默认 case 仅用于快速验证，不代表正式测试集。
    input_frame = int32([32 32 32; 64 48 32; 96 96 96; 168 168 224]);
end

runtime = ce_hw_control_update(input_frame, cfg, prev_state);
if strcmpi(mode, 'gain')
    datapath = ce_hw_datapath(input_frame, runtime, cfg, 'gain');
else
    datapath = ce_hw_datapath(input_frame, runtime, cfg, 'rgb');
end

result = struct();
result.cfg = cfg;
result.runtime = runtime;
result.datapath = datapath;
result.scene_id = runtime.scene_id;
result.scene_name = runtime.scene_name;
result.raw_scene_name = runtime.raw_scene_name;
result.bypass_flag = runtime.bypass_flag;
