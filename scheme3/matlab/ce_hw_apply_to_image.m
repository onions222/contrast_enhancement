function result = ce_hw_apply_to_image(image_in, cfg, prev_state)
%CE_HW_APPLY_TO_IMAGE 对单张图像运行方案三，并返回可保存结果。
% 说明：
%   - 这是图像运行外壳，不属于核心硬件路径
%   - RGB 输入走 V 域统计 + gain x RGB 输出
%   - 灰度输入走 value/tone 输出

image_u8 = uint8(image_in);

if ndims(image_u8) == 2
    value_plane = int32(image_u8(:));
    runtime = ce_hw_control_update(value_plane, cfg, prev_state);
    datapath = ce_hw_datapath(value_plane, runtime, cfg, 'rgb');
    output_image = reshape(uint8(datapath.tone_out(:)), size(image_u8, 1), size(image_u8, 2));
else
    rows = size(image_u8, 1);
    cols = size(image_u8, 2);
    rgb_in = int32(reshape(image_u8, rows * cols, 3));
    runtime = ce_hw_control_update(rgb_in, cfg, prev_state);
    datapath = ce_hw_datapath(rgb_in, runtime, cfg, 'rgb');
    output_image = uint8(reshape(datapath.rgb_out, rows, cols, 3));
end

result = struct();
result.input_image = image_u8;
result.runtime = runtime;
result.datapath = datapath;
result.output_image = output_image;
result.state_out = runtime.state_out;
end
