# 方案一 MATLAB 定点交付包

本目录提供方案一 `Percentile-Anchored PWL` 的 MATLAB 定点实现，目标是交接给数字 IC 设计工程师进行控制路径和数据路径联调。

## 文件说明

- `ce1_hw_config.m`
  冻结寄存器默认值、Q8 常量、位宽说明和可调参数。
- `ce1_hw_control_update.m`
  帧级控制路径：输入归一化、直方图、percentile anchor、gain cap、anchor 扩展、4 点 PWL、256 点 LUT、单调约束、temporal IIR。
- `ce1_hw_datapath.m`
  像素级查表路径：只做灰度查表和输出饱和。
- `ce1_hw_apply_to_image.m`
  单张图片运行外壳：读取图像矩阵，在 V 域统计后把增强结果写回灰度图或 RGB 图。
  对 RGB 输入，默认使用保守的 `rgb_gain_blend`，不是直接 full gain 回写。
- `ce1_hw_make_compare_image.m`
  把原图和增强图拼接成“左原图、右增强图”的双联图，用于磁盘保存。
- `ce1_hw_apply_to_video_frame.m`
  单帧视频图像运行外壳：在 V 域统计，并把 `runtime.state_out` 交给视频入口做跨帧传递。
- `run_ce1_hw_image.m`
  单张图片读盘、运行并保存双联图结果。
- `run_ce1_hw_folder.m`
  读取文件夹内图片，批量运行并保存双联图结果到输出目录。
- `run_ce1_hw_video.m`
  读取单个视频文件，按帧顺序运行并保存增强后视频。
- `validate_ce1_hw_against_python.m`
  用于逐项数值检查。
- `ce1_hw_runtime_design.md`
  交付型说明文档，集中列公式、位宽、寄存器建议和实现约束。

## 定点规则

- 比例类参数统一采用 `Q8`
  例如 `0.4 -> 102`，表示运行时真实值为 `102 / 256`
- 像素、PWL 坐标、tone LUT 统一采用 `U8.0`
- 所有核心算法只用整数运算
- 核心路径不调用 `round/min/max/sum/histcounts/interp1/mean` 这类高层数值函数
- 控制路径和数据路径内部不再拆 helper，所有关键步骤顺序展开

## RGB 回写策略

- 统计域仍然是 HSV 的 `V` 域，即逐像素 `max(R,G,B)`
- 先在 `V` 域生成 `tone_lut`，再得到 `V_out`
- 对 RGB 图，默认不直接使用完整增益：

```text
gain_raw = V_out / max(V_in, 1)
gain_blend = 1 + beta * (gain_raw - 1)
```

- 其中 `beta = rgb_gain_blend_q8 / 256`
- 当前默认 `beta = 0.25`

这样做的目的，是减轻以下场景的块状感和斑驳感：
- 人脸皮肤 close-up
- 平滑高光区
- 因 `V` 域 LUT 跳变直接乘回 RGB 带来的局部增益起伏

## 典型用法

```matlab
addpath('scheme1/matlab');
cfg = ce1_hw_config();
run('scheme1/matlab/run_ce1_hw_image.m');
image_result
run('scheme1/matlab/run_ce1_hw_folder.m');
folder_result
run('scheme1/matlab/run_ce1_hw_video.m');
video_result
report = validate_ce1_hw_against_python();
disp(report.all_pass);
```

## 说明

- 本目录不依赖 `scheme3/matlab/`
- `run_ce1_hw_image.m` 和 `run_ce1_hw_folder.m` 是逐图独立处理
- 这两个图片入口保存的是双联图：左侧原图，右侧增强图
- `run_ce1_hw_video.m` 会在整段视频内连续传递 `prev_state`
- RGB 图片和视频入口默认使用保守的 `rgb_gain_blend`，不是 full gain 回写
- 验证脚本入口位于 [export_percentile_pwl_reference.py](/Users/onion/Desktop/code/Contrast/scheme1/eval/export_percentile_pwl_reference.py)
