# Scheme1 MATLAB Video Entry Design

## Goal

为 `scheme1/matlab` 增加一套读取视频文件、按帧顺序增强、并将结果保存为视频文件的 MATLAB 入口。视频增强链路必须沿整段视频连续传递 `prev_state`，使 temporal smoothing / LUT state 真正按照时间顺序生效，而不是像当前图片/文件夹入口那样逐帧独立重置。

## Scope

本设计只修改 `scheme1/matlab`，不修改任何 Python 路径，也不修改 `scheme3`。

本次只交付：
- 一个视频运行入口脚本
- 一个视频帧处理外壳
- `README` 中的视频使用说明

本次不交付：
- 视频级调试日志导出
- 每帧 LUT/anchor/gain CSV 导出
- 音频保留
- 多编码格式兼容层
- `scheme3` 视频入口

## Existing Context

当前 `scheme1/matlab` 已经具备：
- `ce1_hw_control_update.m`
- `ce1_hw_datapath.m`
- `ce1_hw_apply_to_image.m`
- `run_ce1_hw_image.m`
- `run_ce1_hw_folder.m`

当前能力是：
1. 读取单张图片
2. 读取文件夹里的图片
3. 每张图都基于当前图像自身统计量生成 LUT
4. 图片路径的 `prev_state` 不跨图片持续传递

因此当前并不是真正的视频增强，只是“按图像批处理”。

## Requirements

### Functional

1. 能读取一个视频文件。
2. 能逐帧执行 `scheme1` 的增强。
3. 第 `t` 帧的 `runtime.state_out` 必须传递给第 `t+1` 帧。
4. 输出增强后的视频文件到仓库根目录下的 `outputs/scheme1`。
5. 支持 RGB 视频输入。
6. 统计域继续使用 HSV 的 `V` 域，即逐像素 `max(R,G,B)`。

### Behavioral

1. 第一帧使用 identity LUT 初始化 `prev_state`。
2. 后续帧沿视频顺序连续传递状态。
3. 输出视频分辨率与输入一致。
4. 输出视频帧率默认与输入一致。
5. 每帧增强方式与现有图片入口保持一致：
   - 先在 `V` 域生成 `tone_lut`
   - 再使用 `V_out / max(V_in, 1)` 形成逐像素 gain
   - 再乘回 RGB

## Design Options

### Option A: 单脚本视频入口

在 `run_ce1_hw_video.m` 里直接完成：
- 视频读写
- 帧级状态传递
- `V` 计算
- 控制路径
- 数据路径
- RGB 回写

优点：
- 改动最少
- 最快打通视频主链路

缺点：
- 脚本会变长
- 后续扩展调试信息时更难维护

### Option B: 视频入口 + 帧处理外壳

新增：
- `ce1_hw_apply_to_video_frame.m`
- `run_ce1_hw_video.m`

其中：
- `run_ce1_hw_video.m` 负责视频读写、循环和状态传递
- `ce1_hw_apply_to_video_frame.m` 负责对单帧 RGB 做 `V` 域增强并返回 `state_out`

优点：
- 边界更清晰
- 与现有 `ce1_hw_apply_to_image.m` 的职责保持一致
- 后续如果要加 frame log/export，更容易扩展

缺点：
- 比单脚本多一层封装

### Recommendation

采用 **Option B**。

原因：
- 视频读写和单帧算法处理的职责天然不同
- `prev_state` 的时序传递逻辑应该留在视频外层，而不是藏在图像外壳里
- 这样可以最大化复用现有控制路径/数据路径，同时保持视频入口清晰可读

## Architecture

### New Files

新增：
- `scheme1/matlab/ce1_hw_apply_to_video_frame.m`
- `scheme1/matlab/run_ce1_hw_video.m`

修改：
- `scheme1/matlab/README.md`

### Responsibilities

#### `ce1_hw_apply_to_video_frame.m`

职责：
- 输入一帧 RGB 或灰度图像
- 在 `V` 域构建统计输入
- 调 `ce1_hw_control_update`
- 调 `ce1_hw_datapath`
- 将 `V` 域增强结果转换回 RGB 输出
- 返回：
  - `output_frame`
  - `runtime`
  - `datapath`
  - `state_out`

该文件是“视频帧算法外壳”，不负责视频文件读写。

#### `run_ce1_hw_video.m`

职责：
- 固定默认输入/输出视频路径
- 创建 `VideoReader`
- 创建 `VideoWriter`
- 初始化 `cfg`
- 初始化 `prev_state`
- 按帧顺序调用 `ce1_hw_apply_to_video_frame`
- 将 `state_out` 回灌给下一帧
- 写出增强视频
- 输出最终 summary

该文件是“视频 testbench/runner”，不承担硬件核心算法定义。

## Data Flow

每帧数据流如下：

1. 读入 `RGB_t`
2. 计算 `V_t = max(R_t, G_t, B_t)`
3. `runtime_t = ce1_hw_control_update(V_t, cfg, prev_state_{t-1})`
4. `datapath_t = ce1_hw_datapath(V_t, runtime_t, cfg)`
5. 得到 `V'_t = datapath_t.mapped_frame`
6. 计算逐像素 gain：

   `gain_t(x,y) = V'_t(x,y) / max(V_t(x,y), 1)`

7. 回写 RGB：

   `R'_t = clip(R_t * gain_t)`

   `G'_t = clip(G_t * gain_t)`

   `B'_t = clip(B_t * gain_t)`

8. `prev_state_t = runtime_t.state_out`
9. 将 `prev_state_t` 传给下一帧

## Temporal State Policy

视频入口必须采用“整段视频连续传递状态”的策略：

- 第 1 帧：
  - `prev_lut_valid = 0`
  - `prev_lut = identity_lut`

- 第 `t` 帧：
  - `prev_state = state_out_{t-1}`

这样才能使：
- temporal IIR
- bypass 帧回落到 identity 的时域收敛
- 帧间 LUT 平滑

都真正按照视频时间顺序工作。

如果每帧重置 `prev_state`，那么 temporal 行为会完全失效，只剩空间增强。

## I/O Defaults

默认输入视频：
- 放在仓库根目录下用户可直接改写的固定路径

默认输出视频：
- `/Users/onion/Desktop/code/Contrast/outputs/scheme1/ce1_hw_video_output.mp4`

本次不增加命令行参数解析，先保持与现有 MATLAB 脚本一致的“直接改脚本顶部路径再运行”的风格。

## Error Handling

本次只保留最基本的外壳错误处理：
- 若输入视频路径不存在，则直接报错
- 若输出目录不存在，则创建

不增加复杂兼容逻辑，例如：
- 编码格式回退
- 音频流保留
- 多轨流处理

## Testing

### Manual Verification

需要至少验证：

1. `run_ce1_hw_video.m` 能读取一个 RGB 视频并成功生成输出视频。
2. 输出视频尺寸和输入一致。
3. 输出视频帧率与输入一致。
4. 第一帧正常输出。
5. 多帧视频能完整跑完，不在中途因 `prev_state` 结构失配报错。

### Behavioral Verification

需要确认：

1. `prev_state` 在整段视频中持续更新，不被每帧重置。
2. `runtime.state_out.prev_lut_valid` 在第 2 帧之后保持有效。
3. bypass 命中时，视频不会出现因硬切 identity LUT 带来的明显数值异常。

## Non-Goals

本次不做：
- 视频结果与 Python golden 的逐帧对齐验证
- 批量视频目录入口
- `scheme3` 视频入口
- 每帧统计日志导出
- 音频复用

## Success Criteria

满足以下条件即视为完成：

1. `scheme1/matlab` 新增视频入口脚本。
2. 视频脚本能读取一个视频并输出增强后视频。
3. `prev_state` 在整段视频中连续传递。
4. 输出视频保存到 `outputs/scheme1`。
5. README 中新增视频入口的使用说明。
