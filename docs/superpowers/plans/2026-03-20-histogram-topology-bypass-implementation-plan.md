# Histogram Topology Bypass Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用基于 `mask / popcount / run-count` 的直方图拓扑 bypass 替换 `scheme1` 当前的 `dense / sparse / comb` 三路 bypass。

**Architecture:** 在 `scheme1` 中把 bypass 重构成统一的拓扑特征提取和三层判定链路：`uniform_sparse`、`disconnected_comb`、`continuous_artificial`。Python 浮点模型与 MATLAB 固定点模型共享同一套规则语义，但各自独立实现，不复用函数。测试覆盖人工 pattern、自然图像代理样本和规则边界。 

**Tech Stack:** Python, NumPy, MATLAB, pytest

---

## File Map

- Modify: `scheme1/src/ce_scheme1/percentile_pwl.py`
  - 替换现有 `dense/sparse/comb` bypass 特征与判定逻辑
- Modify: `scheme1/matlab/ce1_pattern_bypass.m`
  - 替换为 `mask/A/C/R/F/Pmax` 规则
- Modify: `scheme1/matlab/ce1_hw_control_update.m`
  - 对接新的 bypass reason / 输出字段
- Modify: `scheme1/matlab/ce1_hw_runtime_design.md`
  - 更新 bypass 设计说明
- Modify: `scheme1/tests/test_float_pattern_bypass.py`
  - 改写为新规则测试
- Modify: `scheme1/tests/test_percentile_pwl_temporal.py`
  - 如有旧 bypass reason 断言，改成新枚举
- Create or Modify: `scripts/analyze_histogram_stats.py`
  - 增加 `A/C/R/F/Pmax` 统计输出，辅助调阈值

## Chunk 1: Python Topology Features

### Task 1: 写拓扑特征 failing tests

**Files:**
- Modify: `scheme1/tests/test_float_pattern_bypass.py`
- Modify: `scheme1/src/ce_scheme1/percentile_pwl.py`

- [ ] **Step 1: 写特征提取测试**

增加测试，覆盖：
- `A`
- `C`
- `R = A - C`
- `F`

示例：

```python
def test_topology_features_for_two_isolated_bins():
    model = FloatPercentilePwlModel()
    features = model._topology_features_from_hist([10, 0, 10] + [0] * 29, total_pixels=20)
    assert features["active_count"] == 2
    assert features["connectivity_count"] == 0
    assert features["run_count"] == 2
    assert features["span_count"] == 3
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest scheme1/tests/test_float_pattern_bypass.py -q`

Expected: FAIL，提示新特征或新字段尚未实现。

- [ ] **Step 3: 在 Python 模型中实现拓扑特征提取**

在 `scheme1/src/ce_scheme1/percentile_pwl.py` 中新增 focused helper：
- 从 `32-bin histogram` 生成 thresholded `mask`
- 计算 `A/C/R/F/Pmax`

不要保留旧的 `sum_abs_diff / hole_count / active_run_count` 主路径依赖。

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest scheme1/tests/test_float_pattern_bypass.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scheme1/src/ce_scheme1/percentile_pwl.py scheme1/tests/test_float_pattern_bypass.py
git commit -m "Implement topology bypass features in scheme1 Python model"
```

## Chunk 2: Python Bypass Rules

### Task 2: 写新规则 failing tests

**Files:**
- Modify: `scheme1/tests/test_float_pattern_bypass.py`
- Modify: `scheme1/src/ce_scheme1/percentile_pwl.py`

- [ ] **Step 1: 写规则级测试**

覆盖至少三类：
- `uniform_sparse`
- `disconnected_comb`
- `continuous_artificial`

示例：

```python
def test_uniform_sparse_hits_single_bin_pattern():
    model = FloatPercentilePwlModel()
    result = model.process_frame([32] * 256)
    assert result.stats["pattern_bypass"] is True
    assert result.stats["pattern_bypass_reason"] == "uniform_sparse"
```

```python
def test_disconnected_comb_hits_step_like_distribution():
    ...
```

```python
def test_continuous_artificial_hits_full_ramp():
    ...
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest scheme1/tests/test_float_pattern_bypass.py -q`

Expected: FAIL，reason 仍是旧的 `dense/sparse/comb` 或规则行为不匹配。

- [ ] **Step 3: 实现新规则链**

在 `scheme1/src/ce_scheme1/percentile_pwl.py` 中：
- 删除 `dense_gradient / sparse_pattern / comb_pattern` 判定
- 改为：
  - `uniform_sparse`
  - `disconnected_comb`
  - `continuous_artificial`
- reason 字段只输出新枚举

- [ ] **Step 4: 跑规则测试**

Run: `pytest scheme1/tests/test_float_pattern_bypass.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scheme1/src/ce_scheme1/percentile_pwl.py scheme1/tests/test_float_pattern_bypass.py
git commit -m "Replace scheme1 bypass rules with topology logic"
```

## Chunk 3: Python Integration And Regression

### Task 3: 验证主流程集成

**Files:**
- Modify: `scheme1/tests/test_percentile_pwl_temporal.py`
- Modify: `scheme1/src/ce_scheme1/percentile_pwl.py`

- [ ] **Step 1: 更新主流程断言**

若现有测试中依赖旧 bypass reason 或旧特征字段，改成新字段。

- [ ] **Step 2: 添加一条“命中 bypass 后 identity LUT”测试**

```python
def test_topology_bypass_forces_identity_lut():
    ...
```

- [ ] **Step 3: 运行 scheme1 全量测试**

Run: `pytest scheme1/tests -q`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add scheme1/tests/test_percentile_pwl_temporal.py scheme1/src/ce_scheme1/percentile_pwl.py
git commit -m "Integrate topology bypass into scheme1 frame pipeline"
```

## Chunk 4: MATLAB Topology Bypass

### Task 4: 写 MATLAB 规则实现

**Files:**
- Modify: `scheme1/matlab/ce1_pattern_bypass.m`
- Modify: `scheme1/matlab/ce1_hw_control_update.m`

- [ ] **Step 1: 先对照 Python 规则更新 MATLAB 输出字段**

把 reason 改为：
- `uniform_sparse`
- `disconnected_comb`
- `continuous_artificial`

- [ ] **Step 2: 重写 MATLAB bypass 主体**

在 `scheme1/matlab/ce1_pattern_bypass.m` 中实现：
- `mask generation`
- `A`
- `C`
- `R`
- `F`
- `Pmax`
- 新三层规则

保留纯整数实现，不使用浮点。

- [ ] **Step 3: 对接 control update**

确保 `ce1_hw_control_update.m` 使用新的 bypass 输出，不再引用旧 reason。

- [ ] **Step 4: 手工运行 MATLAB case**

Run:

```bash
/Applications/MATLAB_R2025a.app/bin/matlab -batch "cd('/Users/onion/Desktop/code/Contrast'); addpath('scheme1/matlab'); run('scheme1/matlab/run_ce1_hw_case.m');"
```

Expected: 正常输出 `result`，无字段错误。

- [ ] **Step 5: Commit**

```bash
git add scheme1/matlab/ce1_pattern_bypass.m scheme1/matlab/ce1_hw_control_update.m
git commit -m "Implement topology bypass in scheme1 MATLAB model"
```

## Chunk 5: Offline Threshold Analysis

### Task 5: 补充离线分析脚本

**Files:**
- Modify: `scripts/analyze_histogram_stats.py`

- [ ] **Step 1: 增加新统计输出**

输出：
- `A`
- `C`
- `R`
- `F`
- `Pmax`
- `bypass_reason`

- [ ] **Step 2: 运行脚本**

Run: `python scripts/analyze_histogram_stats.py`

Expected: 能打印 starter synth 图的拓扑统计和规则命中结果。

- [ ] **Step 3: Commit**

```bash
git add scripts/analyze_histogram_stats.py
git commit -m "Add topology bypass offline analysis output"
```

## Chunk 6: Docs And Final Verification

### Task 6: 更新设计文档并全量验证

**Files:**
- Modify: `scheme1/matlab/ce1_hw_runtime_design.md`

- [ ] **Step 1: 更新 MATLAB 设计文档**

补充：
- `mask / A / C / R / F / Pmax`
- 新 bypass 规则
- 为什么替代旧三路

- [ ] **Step 2: 运行 Python 全量测试**

Run: `pytest scheme1/tests scheme3/tests -q`

Expected: PASS

- [ ] **Step 3: 运行全仓测试**

Run: `pytest -q`

Expected: PASS

- [ ] **Step 4: 运行 MATLAB 验证**

Run:

```bash
/Applications/MATLAB_R2025a.app/bin/matlab -batch "cd('/Users/onion/Desktop/code/Contrast'); addpath('scheme1/matlab'); run('scheme1/matlab/run_ce1_hw_batch.m');"
```

Expected: 正常运行，无字段错误。

- [ ] **Step 5: Final Commit**

```bash
git add scheme1/matlab/ce1_hw_runtime_design.md
git commit -m "Finalize topology bypass migration for scheme1"
```
