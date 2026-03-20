%RUN_CE1_HW_IMAGE 方案一单张图片运行脚本。
% 用法：
%   - 直接运行本脚本，读取 input_image_path，输出到 output_image_path
%
% 输出：
%   - image_result: 结构体，包含输入图、V 平面、runtime、datapath、输出图

repo_root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
input_image_path = fullfile(repo_root, 'data', 'raw', 'wikimedia_commons', 'text_ui_talad_neon_night_market_signage.jpg');
output_root = fullfile(repo_root, 'outputs', 'scheme1');
if ~exist(output_root, 'dir')
    mkdir(output_root);
end
output_image_path = fullfile(output_root, 'ce1_hw_single_output.png');

cfg = ce1_hw_config();
prev_state = struct( ...
    'prev_lut_valid', uint8(0), ...
    'prev_lut', uint16(cfg.identity_lut(:)));

input_image = imread(input_image_path);
image_result = ce1_hw_apply_to_image(input_image, cfg, prev_state);
imwrite(image_result.output_image, output_image_path);

disp('scheme1 single-image run');
disp(['input_image_path = ' input_image_path]);
disp(['output_image_path = ' output_image_path]);
disp(['pattern_bypass = ' num2str(double(image_result.runtime.pattern_bypass_flag)) ...
    ', reason = ' image_result.runtime.pattern_bypass_reason]);
disp(['rows = ' num2str(size(image_result.output_image, 1)) ...
    ', cols = ' num2str(size(image_result.output_image, 2))]);
