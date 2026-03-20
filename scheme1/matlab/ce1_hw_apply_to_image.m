function result = ce1_hw_apply_to_image(image_in, cfg, prev_state)
%CE1_HW_APPLY_TO_IMAGE 对单张图像运行方案一，并返回可保存结果。
% 说明：
%   - 这是图像运行外壳，不属于硬件核心路径
%   - 允许使用 imread/imwrite 所需的图像矩阵操作
%   - 控制路径统计域仍然是 HSV 的 V 域，即逐像素 max(R,G,B)

% cfg: 运行配置，必须显式传入。
% prev_state: 时域状态结构，必须显式传入。

image_u8 = uint8(image_in);

if ndims(image_u8) == 2
    % 灰度输入直接视为 V 平面。
    value_plane = uint16(image_u8);
    runtime = ce1_hw_control_update(value_plane, cfg, prev_state);
    datapath = ce1_hw_datapath(value_plane, runtime, cfg);
    output_image = uint8(datapath.mapped_frame);
else
    % RGB 输入先取 V = max(R,G,B)。
    red_plane = uint16(image_u8(:, :, 1));
    green_plane = uint16(image_u8(:, :, 2));
    blue_plane = uint16(image_u8(:, :, 3));
    value_plane = max(max(red_plane, green_plane), blue_plane);

    runtime = ce1_hw_control_update(value_plane, cfg, prev_state);
    datapath = ce1_hw_datapath(value_plane, runtime, cfg);

    % V_out / max(V_in, 1) 形成逐像素 gain，再乘回 RGB。
    value_out = double(datapath.mapped_frame);
    value_in = double(value_plane);
    value_in_safe = value_in;
    value_in_safe(value_in_safe == 0) = 1;
    gain_map = value_out ./ value_in_safe;

    rgb_out = zeros(size(image_u8), 'uint8');
    channel_index = 1;
    while channel_index <= 3
        channel_in = double(image_u8(:, :, channel_index));
        channel_out = channel_in .* gain_map;
        channel_out(channel_out < 0) = 0;
        channel_out(channel_out > 255) = 255;
        rgb_out(:, :, channel_index) = uint8(round(channel_out));
        channel_index = channel_index + 1;
    end
    output_image = rgb_out;
end

result = struct();
result.input_image = image_u8;
result.value_plane = uint16(value_plane);
result.runtime = runtime;
result.datapath = datapath;
result.output_image = uint8(output_image);
result.state_out = runtime.state_out;
end
