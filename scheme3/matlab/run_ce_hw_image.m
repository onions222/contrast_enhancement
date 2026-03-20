%RUN_CE_HW_IMAGE 方案三单张图片运行脚本。
% 用法：
%   - 直接运行本脚本，读取 input_image_path，输出到 output_image_path
%
% 输出：
%   - image_result: 结构体，包含 runtime、datapath 和输出图像

repo_root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
input_image_path = fullfile(repo_root, 'data', 'raw', 'starter_synth_v1', 'high_key_window_soft.png');
output_root = fullfile(repo_root, 'outputs', 'scheme3');
if ~exist(output_root, 'dir')
    mkdir(output_root);
end
output_image_path = fullfile(output_root, 'ce_hw_single_output.png');

cfg = ce_hw_config();
prev_state = struct();

input_image = imread(input_image_path);
image_result = ce_hw_apply_to_image(input_image, cfg, prev_state);
imwrite(image_result.output_image, output_image_path);

disp('scheme3 single-image run');
disp(['input_image_path = ' input_image_path]);
disp(['output_image_path = ' output_image_path]);
disp(['scene_name = ' image_result.runtime.scene_name]);
disp(['bypass_flag = ' num2str(double(image_result.runtime.bypass_flag))]);
