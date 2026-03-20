%RUN_CE1_HW_VIDEO 方案一视频运行脚本。
% 用法：
%   - 直接运行本脚本，读取 input_video_path，输出到 output_video_path
%
% 说明：
%   - 本脚本按视频帧顺序连续传递 prev_state
%   - 第 t 帧的 state_out 会直接作为第 t+1 帧的 prev_state
%   - 这样 temporal IIR / LUT 平滑才会在整段视频内真正生效

repo_root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
input_video_path = fullfile(repo_root, 'outputs', 'scheme1', 'ce1_hw_video_input.mp4');
output_root = fullfile(repo_root, 'outputs', 'scheme1');
if ~exist(output_root, 'dir')
    mkdir(output_root);
end
output_video_path = fullfile(output_root, 'ce1_hw_video_output.mp4');

if ~exist(input_video_path, 'file')
    error('run_ce1_hw_video:missingInput', ['input video not found: ' input_video_path]);
end

cfg = ce1_hw_config();
prev_state = struct( ...
    'prev_lut_valid', uint8(0), ...
    'prev_lut', uint16(cfg.identity_lut(:)));

reader = VideoReader(input_video_path);
writer = VideoWriter(output_video_path, 'MPEG-4');
writer.FrameRate = reader.FrameRate;
open(writer);

frame_count = uint32(0);
last_pattern_bypass = uint8(0);
last_bypass_reason = '';
last_rows = uint32(0);
last_cols = uint32(0);

while hasFrame(reader)
    frame_in = readFrame(reader);
    frame_result = ce1_hw_apply_to_video_frame(frame_in, cfg, prev_state);
    writeVideo(writer, frame_result.output_frame);

    prev_state = frame_result.state_out;
    frame_count = frame_count + uint32(1);
    last_pattern_bypass = frame_result.runtime.pattern_bypass_flag;
    last_bypass_reason = frame_result.runtime.pattern_bypass_reason;
    last_rows = uint32(size(frame_result.output_frame, 1));
    last_cols = uint32(size(frame_result.output_frame, 2));
end

close(writer);

video_result = struct();
video_result.input_video_path = input_video_path;
video_result.output_video_path = output_video_path;
video_result.frame_count = frame_count;
video_result.frame_rate = reader.FrameRate;
video_result.rows = last_rows;
video_result.cols = last_cols;
video_result.last_pattern_bypass = last_pattern_bypass;
video_result.last_bypass_reason = last_bypass_reason;
video_result.final_state = prev_state;

disp('scheme1 video run');
disp(['input_video_path = ' input_video_path]);
disp(['output_video_path = ' output_video_path]);
disp(['frame_count = ' num2str(double(frame_count))]);
disp(['frame_rate = ' num2str(double(reader.FrameRate))]);
disp(['rows = ' num2str(double(last_rows)) ', cols = ' num2str(double(last_cols))]);
disp(['last_pattern_bypass = ' num2str(double(last_pattern_bypass)) ...
    ', reason = ' last_bypass_reason]);
