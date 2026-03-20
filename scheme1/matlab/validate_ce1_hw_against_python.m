function report = validate_ce1_hw_against_python(cfg)
%VALIDATE_CE1_HW_AGAINST_PYTHON 方案一 MATLAB 与 Python golden 对齐验证。
% 说明：
%   - 这是验证外壳，不属于硬件核心路径
%   - 允许使用系统调用和 JSON 解析

if nargin < 1 || isempty(cfg)
    cfg = ce1_hw_config();
end

repo_root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
python_script = fullfile(repo_root, 'scheme1', 'eval', 'export_percentile_pwl_reference.py');
json_path = [tempname '.json'];
command = ['python "' python_script '" "' json_path '"'];
[status, cmdout] = system(command);
if status ~= 0
    error('Python golden export failed: %s', cmdout);
end

raw_text = fileread(json_path);
python_report = jsondecode(raw_text);

cases = cell(4, 1);
cases{1} = {uint16([])};
cases{2} = {uint16([32 32 32 96 96 96 160 160 160])};
cases{3} = {uint16([120 120 120 122 122 122 124 124 124])};
cases{4} = {
    uint16([32 32 32 128 128 128 196 196 196]), ...
    uint16([40 40 40 136 136 136 204 204 204])};

report = struct();
report.all_pass = true;
report.case_count = uint32(numel(cases));
report.frame_count = uint32(0);
report.details = cell(numel(cases), 1);

case_index = 1;
while case_index <= numel(cases)
    frames = cases{case_index};
    py_case = python_report.cases(case_index);
    state = struct( ...
        'prev_lut_valid', uint8(0), ...
        'prev_lut', uint16(cfg.identity_lut(:)));
    frame_details = cell(numel(frames), 1);
    frame_index = 1;
    while frame_index <= numel(frames)
        runtime = ce1_hw_control_update(frames{frame_index}, cfg, state);
        datapath = ce1_hw_datapath(frames{frame_index}, runtime, cfg);
        state = runtime.state_out;

        py_frame = py_case.frames(frame_index);
        hist_match = isequal(uint32(runtime.histogram(:)), uint32(py_frame.histogram32(:)));
        lut_match = isequal(uint16(runtime.tone_lut(:)), uint16(py_frame.lut(:)));
        map_match = isequal(uint16(datapath.mapped_samples(:)), uint16(py_frame.mapped_samples(:)));
        p_low_match = double(runtime.p_low) == double(py_frame.p_low);
        p_high_match = double(runtime.p_high) == double(py_frame.p_high);
        anchor_low_match = double(runtime.anchor_low) == double(py_frame.anchor_low);
        anchor_high_match = double(runtime.anchor_high) == double(py_frame.anchor_high);
        gain_nominal_match = double(runtime.gain_nominal_q8) == double(py_frame.gain_nominal_q8);
        gain_match = double(runtime.gain_q8) == double(py_frame.gain_q8);

        frame_pass = hist_match && lut_match && map_match && p_low_match && p_high_match && ...
            anchor_low_match && anchor_high_match && gain_nominal_match && gain_match;

        if ~frame_pass
            report.all_pass = false;
        end

        frame_details{frame_index} = struct( ...
            'name', py_frame.name, ...
            'histogram_match', hist_match, ...
            'lut_match', lut_match, ...
            'mapped_match', map_match, ...
            'p_low_match', p_low_match, ...
            'p_high_match', p_high_match, ...
            'anchor_low_match', anchor_low_match, ...
            'anchor_high_match', anchor_high_match, ...
            'gain_nominal_match', gain_nominal_match, ...
            'gain_match', gain_match, ...
            'frame_pass', frame_pass);

        report.frame_count = report.frame_count + uint32(1);
        frame_index = frame_index + 1;
    end
    report.details{case_index} = frame_details;
    case_index = case_index + 1;
end

disp(['scheme1 python alignment all_pass = ' num2str(double(report.all_pass))]);
end
