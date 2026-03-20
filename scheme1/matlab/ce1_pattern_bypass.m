function result = ce1_pattern_bypass(histogram32, total_pixels, cfg)
%CE1_PATTERN_BYPASS 基于直方图拓扑的 pattern bypass 检测。
% 目标：
%   - 用统一的 mask / A / C / R / F / Pmax 特征替代旧的 dense/sparse/comb 三路判定
%   - 只保留整数运算，便于映射到 RTL
%
% 输入：
%   histogram32 : 32 x 1 uint32，32-bin 粗直方图
%   total_pixels: uint32，帧总像素数
%   cfg         : struct，需包含 topology bypass 阈值字段
%
% 输出：
%   result.bypass_flag      : uint8，1 = bypass，0 = 正常增强
%   result.bypass_reason    : char，'uniform_sparse' / 'disconnected_comb' / ...
%   result.active_count     : uint8，活跃 bin 数 A
%   result.connectivity_count : uint8，相邻活跃对数 C
%   result.run_count        : uint8，连续段数 R = A - C
%   result.span_count       : uint8，活跃跨度 F
%   result.first_active_bin : uint8
%   result.last_active_bin  : uint8
%   result.max_bin_count    : uint32，最大单 bin 计数 Pmax
%   result.active_mask      : 32 x 1 uint8，活跃掩码
%   result.threshold_count  : uint32，活跃门限

if nargin < 3 || isempty(cfg)
    cfg = ce1_hw_config();
end

n_bins = int32(cfg.pattern_hist_bin_count);

active_mask = zeros(n_bins, 1, 'uint8');
active_count = uint8(0);
connectivity_count = uint8(0);
run_count = uint8(0);
span_count = uint8(0);
first_active_bin = uint8(0);
last_active_bin = uint8(0);
max_bin_count = uint32(0);
found_first = uint8(0);
prev_active = uint8(0);

threshold_count = bitshift(uint32(total_pixels), -int32(cfg.pattern_active_threshold_shift));

if cfg.pattern_bypass_enable == uint8(0)
    result = struct();
    result.bypass_flag = uint8(0);
    result.bypass_reason = '';
    result.active_count = active_count;
    result.connectivity_count = connectivity_count;
    result.run_count = run_count;
    result.span_count = span_count;
    result.first_active_bin = first_active_bin;
    result.last_active_bin = last_active_bin;
    result.max_bin_count = max_bin_count;
    result.active_mask = uint8(active_mask(:));
    result.threshold_count = uint32(threshold_count);
    return;
end

bin_index = int32(0);
while bin_index < n_bins
    count = uint32(histogram32(bin_index + 1));
    current_active = uint8(0);

    if count > max_bin_count
        max_bin_count = count;
    end

    if count > threshold_count
        current_active = uint8(1);
        active_mask(bin_index + 1) = uint8(1);
        active_count = active_count + uint8(1);
        last_active_bin = uint8(bin_index);

        if found_first == uint8(0)
            first_active_bin = uint8(bin_index);
            found_first = uint8(1);
        end

        if prev_active == uint8(1)
            connectivity_count = connectivity_count + uint8(1);
        else
            run_count = run_count + uint8(1);
        end
    end

    prev_active = current_active;
    bin_index = bin_index + int32(1);
end

if active_count > uint8(0)
    span_count = uint8(int32(last_active_bin) - int32(first_active_bin) + 1);
end

bypass_flag = uint8(0);
bypass_reason = '';

% Rule 1: Uniform / Sparse
if active_count <= uint8(cfg.pattern_uniform_sparse_active_max)
    bypass_flag = uint8(1);
    bypass_reason = 'uniform_sparse';
end

% Rule 2: Disconnected / Comb
if bypass_flag == uint8(0)
    lhs_runs = int32(run_count) * int32(cfg.pattern_disconnected_comb_runs_mul);
    rhs_runs = int32(active_count);
    if lhs_runs > rhs_runs
        bypass_flag = uint8(1);
        bypass_reason = 'disconnected_comb';
    end
end

% Rule 3: Continuous Artificial
if bypass_flag == uint8(0)
    continuous_gate = uint8(1);
    if run_count ~= uint8(1)
        continuous_gate = uint8(0);
    end
    if int32(active_count) < int32(cfg.pattern_continuous_active_min)
        continuous_gate = uint8(0);
    end
    if int32(span_count) < int32(cfg.pattern_continuous_span_min)
        continuous_gate = uint8(0);
    end
    if continuous_gate == uint8(1)
        lhs_peak = int64(max_bin_count) * int64(cfg.pattern_continuous_peak_denom);
        rhs_peak = int64(total_pixels);
        if lhs_peak <= rhs_peak
            bypass_flag = uint8(1);
            bypass_reason = 'continuous_artificial';
        end
    end
end

result = struct();
result.bypass_flag = bypass_flag;
result.bypass_reason = bypass_reason;
result.active_count = active_count;
result.connectivity_count = connectivity_count;
result.run_count = run_count;
result.span_count = span_count;
result.first_active_bin = first_active_bin;
result.last_active_bin = last_active_bin;
result.max_bin_count = max_bin_count;
result.active_mask = uint8(active_mask(:));
result.threshold_count = uint32(threshold_count);
end
