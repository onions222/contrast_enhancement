function report = validate_ce_hw_against_python(cfg)
%VALIDATE_CE_HW_AGAINST_PYTHON 与 Python 风格 golden 的数值对齐验证。
% 说明：
%   - 这是验证外壳，不是核心硬件路径
%   - 目标是输出 max_abs / mean_abs / p95_abs 三个误差统计量
%
% 输入参数：
%   - cfg: 配置 struct，控制 LUT、阈值和位宽定义
%
% 输出参数：
%   - report.max_abs  : 最大绝对误差
%   - report.mean_abs : 平均绝对误差
%   - report.p95_abs  : 95 分位绝对误差
%   - report.case_count: 验证 case 数
%
% 备注：
%   - 本函数保留浮点 golden 外壳用于验证
%   - 不要求映射为硬件路径
%   - 若 max_abs / mean_abs / p95_abs 异常，应优先回查 gain_lut 与 round / 饱和逻辑

if nargin < 1 || isempty(cfg)
    cfg = ce_hw_config();
end

cases = {
    int32([32 32 32; 64 48 32; 96 96 96; 168 168 224]), ...
    int32([168 168 168; 168 168 168; 224 224 224; 224 224 224]), ...
    int32([0 0 0; 8 8 8; 16 16 16; 32 32 32]) ...
};

abs_errors = [];
for idx = 1:numel(cases)
    % 每个 case 独立从空状态启动，避免验证误差被 temporal state 污染。
    frame = cases{idx};
    runtime = ce_hw_control_update(frame, cfg, struct());
    hw = ce_hw_datapath(frame, runtime, cfg, 'rgb');
    golden = local_float_golden(frame, runtime, cfg);
    abs_errors = [abs_errors; abs(double(hw.rgb_out(:)) - double(golden(:)))]; %#ok<AGROW>
end

report = struct();
report.max_abs = max(abs_errors);
report.mean_abs = mean(abs_errors);
report.p95_abs = local_percentile(abs_errors, 95.0);
report.case_count = numel(cases);
end

function golden = local_float_golden(frame, runtime, cfg)
%LOCAL_FLOAT_GOLDEN 使用未量化 gain 重建浮点 golden。
% 输入 frame 为 U8.0/U10.0；tone 来自 U8.0 tone_lut；gain 为验证外壳浮点值。
value_u8 = ce_hw_helpers('rgb_to_value8', frame, cfg.input_bit_depth);
indices = double(value_u8(:)) + 1;
tone = reshape(double(runtime.tone_lut(indices)), [], 1);
gain = zeros(numel(tone), 1);
value_vec = double(value_u8(:));
mask = value_vec > 0;
gain(mask) = tone(mask) ./ value_vec(mask);
gain(~mask) = 0.0;
gain = min(max(gain, 0.0), double(cfg.gain_max) / double(cfg.gain_one));

golden = double(frame) .* gain;
golden = min(max(round(golden), 0), double(2^double(cfg.input_bit_depth) - 1));
end

function p = local_percentile(values, percentile)
%LOCAL_PERCENTILE 验证统计 helper，输出百分位误差。
sorted = sort(double(values(:)));
if isempty(sorted)
    p = 0.0;
    return;
end
rank = (numel(sorted) - 1) * percentile / 100.0;
lower = floor(rank) + 1;
upper = min(lower + 1, numel(sorted));
blend = rank - floor(rank);
p = sorted(lower) + blend * (sorted(upper) - sorted(lower));
end
