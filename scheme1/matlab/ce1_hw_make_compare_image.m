function compare_image = ce1_hw_make_compare_image(input_image, output_image)
%CE1_HW_MAKE_COMPARE_IMAGE 生成“左原图、右增强图”的双联图。
% 说明：
%   - 这是图片保存外壳，不属于硬件核心路径
%   - 输入输出尺寸默认一致
%   - 若为灰度图，则先扩成 3 通道，再做左右拼接

input_u8 = uint8(input_image);
output_u8 = uint8(output_image);

if ndims(input_u8) == 2
    input_rgb = zeros(size(input_u8, 1), size(input_u8, 2), 3, 'uint8');
    input_rgb(:, :, 1) = input_u8;
    input_rgb(:, :, 2) = input_u8;
    input_rgb(:, :, 3) = input_u8;
else
    input_rgb = input_u8;
end

if ndims(output_u8) == 2
    output_rgb = zeros(size(output_u8, 1), size(output_u8, 2), 3, 'uint8');
    output_rgb(:, :, 1) = output_u8;
    output_rgb(:, :, 2) = output_u8;
    output_rgb(:, :, 3) = output_u8;
else
    output_rgb = output_u8;
end

compare_image = cat(2, input_rgb, output_rgb);
end
