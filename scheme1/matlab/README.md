# 方案一 MATLAB 定点交付包

本目录提供方案一 `Percentile-Anchored PWL` 的 MATLAB 定点实现，目标是交接给数字 IC 设计工程师进行控制路径和数据路径联调。

## 文件说明

- `ce1_hw_config.m`
  冻结寄存器默认值、Q8 常量、位宽说明和可调参数。
- `ce1_hw_control_update.m`
  帧级控制路径：输入归一化、直方图、percentile anchor、gain cap、anchor 扩展、5 点 PWL、256 点 LUT、单调约束、temporal IIR。
- `ce1_hw_datapath.m`
  像素级查表路径：只做灰度查表和输出饱和。
- `run_ce1_hw_case.m`
  单 case 运行脚本。
- `run_ce1_hw_batch.m`
  多 case / 多帧运行脚本。
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

## 典型用法

```matlab
addpath('scheme1/matlab');
cfg = ce1_hw_config();
run('scheme1/matlab/run_ce1_hw_case.m');
result
run('scheme1/matlab/run_ce1_hw_batch.m');
summary
report = validate_ce1_hw_against_python();
disp(report.all_pass);
```

若需要自定义输入，可以在运行脚本前先在 workspace 中准备变量：

```matlab
addpath('scheme1/matlab');
cfg = ce1_hw_config(struct('gain_max_q8', uint16(384)));
frame_in = uint16([32 48 64 96; 128 160 192 224]);
run('scheme1/matlab/run_ce1_hw_case.m');

cases = {
    {uint16([32 32 96 96 160 160 224 224])}, ...
    {uint16([120 122 124 126]), uint16([124 126 128 130])}
};
run('scheme1/matlab/run_ce1_hw_batch.m');
```

## 说明

- 本目录不依赖 `scheme3/matlab/`
- 验证脚本入口位于 [export_percentile_pwl_reference.py](/Users/onion/Desktop/code/Contrast/scheme1/eval/export_percentile_pwl_reference.py)
