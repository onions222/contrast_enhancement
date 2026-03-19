# Python 浮点版对比度增强算法可靠性测试文档

## 目标
这份文档定义当前仓库中 Python 浮点版对比度增强算法的可靠性测试范围、测试原因、执行方式、判据，以及当前一轮实现后的结果解释。范围只覆盖 [discrete_scene_gain_float.py](/Users/onion/Desktop/code/Contrast/scheme3/src/ce_scheme3/discrete_scene_gain_float.py) 及其 Python 测试，不包含 MATLAB、硬件运行时、RTL。

核心问题：
- 场景识别是否稳健。
- bypass 是否准确。
- tone curve / gain LUT 是否满足基本规则且符合设计意图。
- 算法是否引入高光洗白、暗部压死、噪声放大、banding、颜色异常、flicker 等副作用。
- 当前失败更像参数问题、场景定义问题、曲线设计问题还是时序策略问题。

## 测试场景总览
| 场景 | 为什么要测 | 怎么测 | 预期结果 |
| --- | --- | --- | --- |
| 同色帧 | 防止低动态范围内容被无意义增强 | 单值灰度帧与单值 RGB 帧，覆盖 `0..240` 多档 | 必须 `bypass=True`，tone 为 identity，gain 为 1，输出逐像素不变 |
| 极低动态范围 | 锁定 bypass 门限 | 两值帧/三值帧，`P98-P2` 分别覆盖 `0..5` | `DR<=4` bypass，`DR>=5` 不 bypass |
| Bright 边界 | 检查高调是否误判 Normal | 围绕 `bright_mean_threshold=176` 和 `bright_ratio_threshold=0.25` 扫描 | 边界单调，无孤岛，阈值以上应稳定进入 Bright |
| Dark I / Dark II 边界 | 检查暗场细节是否被误压成 Dark II | 用 `0 + 64`、`0 + 32` 等低亮/中灰混合比扫描 | 纯近黑更偏 Dark II，带一定中灰细节时优先进入 Dark I |
| 小亮目标 / 小暗目标 | 检查 percentile DR 对小目标的 blind spot | 暗背景亮目标、亮背景暗目标，占比覆盖 `1/2/5/10/25%` | 目标占比足够时不应被 bypass；若被 bypass 要作为 blocker |
| Full ramp | 检查整体单调与 banding | `0..255` ramp | 唯一级数足够，最大 plateau 受限，不出现长台阶 |
| Near-black ramp | 检查暗部梯度保真 | `0..63` ramp | 阴影级数不能明显塌陷，plateau 受限 |
| Near-white ramp | 检查高光细节保真 | `192..255` ramp | 高光段级数保留、不过度顶死 |
| 高调 bucket | 检查高光洗白与过增强 | 亮背景 + 高亮目标的 synthetic bucket | `bright_ratio` 不应系统性上升，高光 `p99` 不应普遍顶死 |
| 暗噪声 bucket | 检查噪声是否被放大 | `base=12`、噪声幅度 `1/2/4/8` | 噪声标准差放大量受控，不触发 scene jitter |
| hold / confirm | 检查切换是否过快或过慢 | `Normal -> Bright -> Bright` 序列 | 第一次只记录 pending，第二次确认后才切换 |
| scene-cut | 检查大变化是否能及时切换 | `abs(mean_t-mean_t-1) >= 32` 的 abrupt 序列 | 首个 cut 帧立即切换到新 scene |
| 慢漂移 | 检查 flicker / LUT jitter | 每帧整体变化 `1 LSB` 的非边界序列 | 不应频繁跳 scene，LUT delta 应稳定 |
| 低照噪声时序 | 检查噪声扰动是否误触发切换 | 多帧低照带随机噪声序列 | raw scene 与 output scene 都应稳定 |
| RGB patch / 肤色块 | 检查颜色关系异常 | 中灰背景 + RGB 肤色块 | 不新增明显通道裁剪，channel ratio drift 受控 |

## 测试方法
### 1. 静态 contract 检查
- 位置：[test_float_scene_config_contract.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/test_float_scene_config_contract.py)
- 目的：锁定当前浮点路径的门限、curve family、strength、gain 上限。
- 判据：
  - 默认阈值和 knots 必须匹配当前基线。
  - `Dark II` 当前策略为更保守的 `dark_ii_strength=0.65`。
  - 四个 scene 的 tone/gain 快照必须稳定。

### 2. 单帧场景分类与 bypass
- 位置：[test_float_scene_classification_boundaries.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/test_float_scene_classification_boundaries.py)、[test_float_scene_bypass.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/test_float_scene_bypass.py)
- 方法：
  - 用占比和亮度参数化构造 100 样本的 synthetic frame。
  - 直接读取 `raw_scene_name / scene_name / bypass_flag / stats`。
- 判据：
  - Bright 边界和 Dark split 必须单调。
  - same-color 和 `DR<=4` 必须精确 bypass。
  - `2%` 亮目标必须逃逸 bypass。
  - `2%` 暗目标目前仍会 bypass，这被保留为“已知行为”，便于后续继续评估。

### 3. Curve / Gain 规则检查
- 位置：[test_float_scene_curves.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/test_float_scene_curves.py)、[test_float_scene_gain_lut.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/test_float_scene_gain_lut.py)
- 方法：
  - 直接检查预生成 scene curve 与 gain LUT。
  - 评估单调性、端点、一阶/二阶差分、最大 gain。
- 判据：
  - tone curve 必须单调，端点必须落在 `(0,255)`。
  - gain 必须非负且 `<= gain_max`。
  - 不允许出现局部尖峰。

### 4. Pattern 质量测试
- 位置：[test_float_scene_patterns_quality.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/test_float_scene_patterns_quality.py)
- 方法：
  - 用 ramp、高调 bucket、暗噪声 bucket 直接比较增强前后。
  - 统计唯一级数、最大 plateau、`bright_ratio`、`p99`、noise std ratio。
- 判据：
  - full ramp 唯一级数 `>=224`。
  - near-black / near-white ramp 唯一级数 `>=48`，最大 plateau `<=2`。
  - 高调 bucket 的 `median Δbright_ratio <= 0.05`。
  - 暗噪声 bucket 的最大 `std_ratio <= 1.35`。

### 5. 时序稳定性
- 位置：[test_float_scene_temporal.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/test_float_scene_temporal.py)
- 方法：
  - 通过 [temporal_runner.py](/Users/onion/Desktop/code/Contrast/scheme3/src/ce_scheme3/temporal_runner.py) 复用同一个模型实例跑序列。
  - 观测 `raw_scene_name / scene_name / lut_mean_abs_delta / enhanced_plane delta`。
- 判据：
  - 非边界慢漂移不允许出现 scene flip。
  - confirm hold 必须在第二次确认时切换。
  - scene-cut 必须在均值突变帧立即切换。

### 6. RGB 路径
- 位置：[test_float_scene_rgb_quality.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/test_float_scene_rgb_quality.py)
- 方法：
  - 用同色 RGB flat 和肤色 patch 检查 `rgb_out`。
  - 计算 clip ratio 和 channel ratio drift。
- 判据：
  - same-color RGB 必须逐像素不变。
  - patch 样本不应出现明显颜色比例漂移，新增裁剪比例需很低。

## 当前一轮结果
### 已经实现的测试文件
- [conftest.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/conftest.py)
- [float_scene_test_utils.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/float_scene_test_utils.py)
- [test_float_scene_config_contract.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/test_float_scene_config_contract.py)
- [test_float_scene_classification_boundaries.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/test_float_scene_classification_boundaries.py)
- [test_float_scene_bypass.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/test_float_scene_bypass.py)
- [test_float_scene_curves.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/test_float_scene_curves.py)
- [test_float_scene_gain_lut.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/test_float_scene_gain_lut.py)
- [test_float_scene_patterns_quality.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/test_float_scene_patterns_quality.py)
- [test_float_scene_temporal.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/test_float_scene_temporal.py)
- [test_float_scene_rgb_quality.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/test_float_scene_rgb_quality.py)
- [test_float_scene_batch_quality.py](/Users/onion/Desktop/code/Contrast/scheme3/tests/test_float_scene_batch_quality.py)

### 本轮发现并处理的失败点
失效现象：
- near-black ramp 在 `Dark II` 场景下只保留 44 个输出灰阶，低于门限 48。

根因：
- 当前 `Dark II` 曲线使用 `family_m_knots` 与 identity 混合。
- 原始 `dark_ii_strength=0.85` 对 0..63 低端压缩过重，造成暗部级数塌陷。

修复策略：
- 不改 scene 分类规则。
- 不改 hold / scene-cut。
- 只把 `Dark II` 的 blend 强度从 `0.85` 下调到 `0.65`，让暗部保留更多层级。

修复后预期：
- near-black ramp 唯一级数从 44 提升到 49。
- high-key、noise、时序与 RGB 测试仍保持通过。

## 如何执行
推荐命令：

```bash
pytest -q scheme3/tests/test_float_scene_config_contract.py \
  scheme3/tests/test_float_scene_classification_boundaries.py \
  scheme3/tests/test_float_scene_bypass.py \
  scheme3/tests/test_float_scene_curves.py \
  scheme3/tests/test_float_scene_gain_lut.py \
  scheme3/tests/test_float_scene_patterns_quality.py \
  scheme3/tests/test_float_scene_temporal.py \
  scheme3/tests/test_float_scene_rgb_quality.py \
  scheme3/tests/test_float_scene_batch_quality.py
```

完整相关 Python 回归：

```bash
pytest -q scheme3/tests/test_reference_model.py \
  scheme3/tests/test_candidate_models.py \
  scheme3/tests/test_float_scene_model.py \
  scheme3/tests/test_metrics.py \
  scheme3/tests/test_patterns.py \
  scheme3/tests/test_temporal_runner.py \
  scheme3/tests/test_batch_runner.py \
  scheme3/tests/test_image_io.py \
  scheme3/tests/test_float_scene_config_contract.py \
  scheme3/tests/test_float_scene_classification_boundaries.py \
  scheme3/tests/test_float_scene_bypass.py \
  scheme3/tests/test_float_scene_curves.py \
  scheme3/tests/test_float_scene_gain_lut.py \
  scheme3/tests/test_float_scene_patterns_quality.py \
  scheme3/tests/test_float_scene_temporal.py \
  scheme3/tests/test_float_scene_rgb_quality.py \
  scheme3/tests/test_float_scene_batch_quality.py
```

## 结果解释规则
- 全部通过：当前 Python 浮点路径通过这轮可靠性门禁，可以进入下一轮更大规模 still/sequence 数据集验证。
- 若 bypass / curve / gain / temporal 规则测试失败：优先视为 blocker。
- 若 bucket 或 pattern 质量测试失败：
  - 单个 synthetic 失败优先归为参数/曲线设计问题。
  - 边界扫描大面积失败优先归为 scene 定义问题。
  - 单帧通过、时序失败优先归为时序策略问题。
