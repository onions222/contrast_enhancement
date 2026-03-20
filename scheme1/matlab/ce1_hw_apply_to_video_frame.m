function result = ce1_hw_apply_to_video_frame(frame_in, cfg, prev_state)
%CE1_HW_APPLY_TO_VIDEO_FRAME 对单帧视频图像运行方案一，并返回时序输出。
% 说明：
%   - 这是视频入口的单帧算法外壳，不属于硬件核心 datapath
%   - 视频级的时序状态传递由上层 video runner 负责
%   - 本文件只负责“当前帧如何被统计、生成 LUT、再写回 RGB”
%   - 控制路径统计域仍然是 HSV 的 V 域，即逐像素 max(R,G,B)
%
% 输入：
%   - frame_in: 当前视频帧，二维灰度或三维 RGB，U8.0
%   - cfg: 固定配置寄存器集合，必须显式传入
%   - prev_state: 上一帧状态，必须显式传入
%
% 输出：
%   - result.input_frame: 当前输入帧
%   - result.value_plane: 当前帧用于统计和查表的 V 平面
%   - result.runtime: 控制路径输出
%   - result.datapath: 数据路径输出
%   - result.output_frame: 当前帧增强结果
%   - result.state_out: 传给下一帧的状态寄存器集合

frame_u8 = uint8(frame_in);

% 灰度帧直接作为 value 输入。
if ndims(frame_u8) == 2
    value_plane = uint16(frame_u8);
    runtime = ce1_hw_control_update(value_plane, cfg, prev_state);
    datapath = ce1_hw_datapath(value_plane, runtime, cfg);
    output_frame = uint8(datapath.mapped_frame);
else
    % RGB 帧先转换到统计域 V = max(R,G,B)。
    red_plane = uint16(frame_u8(:, :, 1));
    green_plane = uint16(frame_u8(:, :, 2));
    blue_plane = uint16(frame_u8(:, :, 3));
    value_plane = max(max(red_plane, green_plane), blue_plane);

    % 先在 V 域生成控制量和增强后的 V_out。
    runtime = ce1_hw_control_update(value_plane, cfg, prev_state);
    datapath = ce1_hw_datapath(value_plane, runtime, cfg);

    % 逐像素 gain = V_out / max(V_in, 1)。
    % 目的：
    %   - 保持 HSV V 域增强的语义
    %   - 让 RGB 三通道共享同一亮度增益，避免单独通道漂移
    value_out = double(datapath.mapped_frame);
    value_in = double(value_plane);
    value_in_safe = value_in;
    value_in_safe(value_in_safe == 0) = 1;
    gain_map = value_out ./ value_in_safe;

    % gain 再乘回 RGB，每个通道分别饱和到 U8.0。
    rgb_out = zeros(size(frame_u8), 'uint8');
    channel_index = 1;
    while channel_index <= 3
        channel_in = double(frame_u8(:, :, channel_index));
        channel_out = channel_in .* gain_map;
        channel_out(channel_out < 0) = 0;
        channel_out(channel_out > 255) = 255;
        rgb_out(:, :, channel_index) = uint8(round(channel_out));
        channel_index = channel_index + 1;
    end
    output_frame = rgb_out;
end

result = struct();
result.input_frame = frame_u8;
result.value_plane = uint16(value_plane);
result.runtime = runtime;
result.datapath = datapath;
result.output_frame = uint8(output_frame);
result.state_out = runtime.state_out;
end
