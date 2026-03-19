# 对比度增强 MATLAB 硬件运行时

本目录提供离散场景对比度增强算法的 MATLAB 硬件运行时包，用于算法交付、定点语义说明、控制路径与数据路径讨论，以及与 Python golden 的早期数值对齐验证。

该包遵循固定的三层拆分：

- `Offline / Control / Datapath`
- `ce_hw_config.m`：冻结默认配置、Q 格式选择、阈值和 curve family knot
- `ce_hw_control_update.m`：完成帧级统计、scene 判决、bypass、tone LUT 和 gain LUT 生成
- `ce_hw_datapath.m`：完成 gain-only 或 `gain x RGB` 的数据路径仿真，并显式实现 round 与饱和

## 文件职责

- `ce_hw_runtime_design.md`：完整的交付型设计说明文档，包含位宽表、寄存器建议和流程图
- `ce_hw_config.m`：默认参数、位宽定义、gain 标度、scene 阈值、curve knot
- `ce_hw_control_update.m`：帧级控制路径更新与运行时 LUT 构建
- `ce_hw_datapath.m`：逐像素数据路径建模
- `ce_hw_helpers.m`：手工定点语义和辅助计算函数
- `run_ce_hw_case.m`：单 case 运行脚本入口
- `run_ce_hw_batch.m`：批量 case 运行脚本入口
- `validate_ce_hw_against_python.m`：与 Python 风格 golden 的误差统计验证入口

## 定点规则摘要

- tone LUT 数据域：`U8.0`，范围 `0..255`
- gain LUT 数据域：`U1.10`，以无符号整数码值保存
- RGB 数据路径乘法回缩：先加 `2^(F-1)`，再右移 `F` 位，实现 round-to-nearest
- 饱和策略：裁剪到合法范围，不使用 wrap

## 典型用法

```matlab
addpath('scheme3/matlab');
cfg = ce_hw_config();
run('scheme3/matlab/run_ce_hw_case.m');
disp(result.scene_name);
run('scheme3/matlab/run_ce_hw_batch.m');
disp(summary.scene_names);
report = validate_ce_hw_against_python();
```

更完整的交付说明请参考 `ce_hw_runtime_design.md`。
