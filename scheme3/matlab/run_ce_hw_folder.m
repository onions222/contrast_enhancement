%RUN_CE_HW_FOLDER 方案三文件夹图片批量运行脚本。
% 用法：
%   - 直接运行本脚本，读取 input_folder，逐张保存到 output_folder
%
% 输出：
%   - folder_result: 结构体，包含输入目录、输出目录、文件数和逐文件摘要

repo_root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
input_folder = fullfile(repo_root, 'data', 'raw', 'starter_synth_v1');
output_root = fullfile(repo_root, 'outputs', 'scheme3');
if ~exist(output_root, 'dir')
    mkdir(output_root);
end
output_folder = fullfile(output_root, 'ce_hw_folder_output');
if ~exist(output_folder, 'dir')
    mkdir(output_folder);
end

cfg = ce_hw_config();

patterns = {'*.png', '*.jpg', '*.jpeg', '*.bmp'};
file_list = [];
pattern_index = 1;
while pattern_index <= numel(patterns)
    file_list = [file_list; dir(fullfile(input_folder, patterns{pattern_index}))]; %#ok<AGROW>
    pattern_index = pattern_index + 1;
end

folder_result = struct();
folder_result.input_folder = input_folder;
folder_result.output_folder = output_folder;
folder_result.file_count = uint32(numel(file_list));
folder_result.files = cell(numel(file_list), 1);

file_index = 1;
while file_index <= numel(file_list)
    file_info = file_list(file_index);
    input_path = fullfile(file_info.folder, file_info.name);
    output_path = fullfile(output_folder, file_info.name);

    prev_state = struct();
    input_image = imread(input_path);
    image_result = ce_hw_apply_to_image(input_image, cfg, prev_state);
    imwrite(image_result.output_image, output_path);

    folder_result.files{file_index} = struct( ...
        'input_path', input_path, ...
        'output_path', output_path, ...
        'scene_name', image_result.runtime.scene_name, ...
        'bypass_flag', image_result.runtime.bypass_flag);
    file_index = file_index + 1;
end

disp('scheme3 folder-image run');
disp(['input_folder = ' input_folder]);
disp(['output_folder = ' output_folder]);
disp(['file_count = ' num2str(double(folder_result.file_count))]);
