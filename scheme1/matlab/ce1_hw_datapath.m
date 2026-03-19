function out = ce1_hw_datapath(frame_in, runtime, cfg)
%CE1_HW_DATAPATH 方案一的灰度查表数据路径。
% 说明：
%   - 方案一当前只支持灰度平面输入
%   - 数据路径只做输入归一化和 tone LUT 查表
%   - 默认输入数据已经满足 unsigned 与位宽约束，不再重复做防御性裁剪

if nargin < 3 || isempty(cfg)
    % 若未显式传参，则加载默认配置寄存器。
    cfg = ce1_hw_config();
end

% 行列计数用于明确对应逐像素扫描顺序。
rows = size(frame_in, 1);
cols = size(frame_in, 2);
total_pixels = rows * cols;

% luma_u8: N x U8.0，按行优先展开后的 LUT 地址输出。
luma_u8 = zeros(total_pixels, 1, 'uint16');
% mapped_samples: N x U8.0，输出像素。
mapped_samples = zeros(total_pixels, 1, 'uint16');
% mapped_frame: rows x cols x U8.0，保留输入平面尺寸。
mapped_frame = zeros(rows, cols, 'uint16');

pixel_index = 1;
row_index = 1;
while row_index <= rows
    % 外层是行扫描，对应 RTL 的 line counter。
    col_index = 1;
    while col_index <= cols
        % 内层是列扫描，对应 RTL 的 pixel counter。
        % raw_sample 默认已经是合法输入码值。
        raw_sample = int32(frame_in(row_index, col_index));

        % 先把输入收敛到 U8.0 LUT 地址域。
        norm_sample = raw_sample;
        if cfg.input_bit_depth > 8
            % 高位宽输入右移到 8bit。
            norm_sample = bitshift(norm_sample, -(int32(cfg.input_bit_depth) - 8));
        elseif cfg.input_bit_depth < 8
            % 低位宽输入左移到 8bit。
            norm_sample = bitshift(norm_sample, 8 - int32(cfg.input_bit_depth));
        end

        % luma_u8 按行优先顺序输出。
        luma_u8(pixel_index) = uint16(norm_sample);
        % LUT 查表就是像素路径唯一的核心运算。
        tone_value = uint16(runtime.tone_lut(norm_sample + 1));
        mapped_samples(pixel_index) = tone_value;
        mapped_frame(row_index, col_index) = tone_value;
        % pixel_index 始终跟随行优先扫描顺序递增。
        pixel_index = pixel_index + 1;
        col_index = col_index + 1;
    end
    row_index = row_index + 1;
end

out = struct();
out.luma_u8 = uint16(luma_u8(:));
out.mapped_samples = uint16(mapped_samples(:));
out.mapped_frame = uint16(mapped_frame);
out.tone_out = uint16(mapped_samples(:));
end
