# Special Continuous Bypass Extension Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `scheme1` 现有 topology bypass 之后新增一个可删除的 `special_continuous_artificial` 后置规则，用来补抓 `ddic_circular_gradient` 和 `ddic_gradient_with_stripes`。

**Architecture:** 保持现有四条主规则不变，只新增 `extrema_count` 与 `edge_pair_count` 两个 shape feature，并把新规则放到最终 `else-if` 分支。Python 与 MATLAB 各自独立实现，不共享代码。测试以“保护特殊图 + 不改主规则 reason + 不新增真实图误判”为中心。

**Tech Stack:** Python, NumPy, MATLAB, pytest

---

## File Map

- Modify: `scheme1/src/ce_scheme1/percentile_pwl.py`
  - 增加 `extrema_count / edge_pair_count`
  - 新增 `special_continuous_artificial` 规则
- Modify: `scheme1/tests/test_float_pattern_bypass.py`
  - 新增失败测试和回归测试
- Modify: `scheme1/matlab/ce1_pattern_bypass.m`
  - 同步实现新增特征与规则
- Modify: `scheme1/matlab/ce1_hw_config.m`
  - 新增可调阈值寄存器
- Modify: `scheme1/matlab/ce1_hw_runtime_design.md`
  - 补充第五条规则说明

## Chunk 1: Python Failing Tests

### Task 1: 先写失败测试锁定目标行为

**Files:**
- Modify: `scheme1/tests/test_float_pattern_bypass.py`

- [ ] **Step 1: 新增两条特殊图命中测试**

增加：

```python
def test_special_continuous_artificial_hits_circular_gradient():
    ...

def test_special_continuous_artificial_hits_gradient_with_stripes():
    ...
```

- [ ] **Step 2: 新增主规则 reason 不变测试**

增加至少三条：
- `gradient_full_ramp` 仍为 `continuous_artificial`
- `gradient_near_black_ramp` 仍为 `narrow_continuous_transition`
- `gray_step_wedge_16` 仍为 `disconnected_comb`

- [ ] **Step 3: 运行失败测试**

Run: `pytest scheme1/tests/test_float_pattern_bypass.py -q`

Expected: FAIL，原因是新 reason 尚未实现，或特殊图仍未命中 bypass。

## Chunk 2: Python Minimal Implementation

### Task 2: 在 Python 中实现后置规则

**Files:**
- Modify: `scheme1/src/ce_scheme1/percentile_pwl.py`

- [ ] **Step 1: 在 topology feature 输出中新增**

新增：
- `extrema_count`
- `edge_pair_count`

- [ ] **Step 2: 新增配置字段**

在 `FloatPercentilePwlConfig` 中增加：
- `pattern_special_continuous_active_min`
- `pattern_special_continuous_span_min`
- `pattern_special_continuous_extrema_max`
- `pattern_special_continuous_edge_pair_min`

- [ ] **Step 3: 把新规则放到最后**

顺序固定：
1. `uniform_sparse`
2. `narrow_continuous_transition`
3. `disconnected_comb`
4. `continuous_artificial`
5. `special_continuous_artificial`

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest scheme1/tests/test_float_pattern_bypass.py -q`

Expected: PASS

## Chunk 3: Python Regression Verification

### Task 3: 验证真实图与全量 scheme1 测试

**Files:**
- Modify: `scheme1/tests/test_float_pattern_bypass.py`

- [ ] **Step 1: 若需要，增加一个真实图风格回归测试**

保持已有 `natural_like` 不被 bypass。

- [ ] **Step 2: 运行 scheme1 全量测试**

Run: `pytest scheme1/tests -q`

Expected: PASS

- [ ] **Step 3: 运行一次离线自然图/特殊图统计脚本**

使用临时 one-shot Python 命令即可，确认：
- 两张特殊图命中
- 现有三张真实误判不新增回来

## Chunk 4: MATLAB Mirror

### Task 4: MATLAB 中同步实现

**Files:**
- Modify: `scheme1/matlab/ce1_hw_config.m`
- Modify: `scheme1/matlab/ce1_pattern_bypass.m`

- [ ] **Step 1: 在 config 中新增阈值寄存器**

- [ ] **Step 2: 在 bypass 中新增**
- `extrema_count`
- `edge_pair_count`
- `special_continuous_artificial`

- [ ] **Step 3: 保持规则顺序一致**

- [ ] **Step 4: 运行 MATLAB case**

Run:

```bash
/Applications/MATLAB_R2025a.app/bin/matlab -batch "cd('/Users/onion/Desktop/code/Contrast'); addpath('scheme1/matlab'); run('scheme1/matlab/run_ce1_hw_case.m');"
```

Expected: 正常运行，无字段错误。

## Chunk 5: Docs And Final Verification

### Task 5: 更新设计文档并做最终验证

**Files:**
- Modify: `scheme1/matlab/ce1_hw_runtime_design.md`

- [ ] **Step 1: 补充第五条规则说明**

- [ ] **Step 2: 运行 Python 与 MATLAB 验证**

Run:
- `pytest scheme1/tests -q`
- `/Applications/MATLAB_R2025a.app/bin/matlab -batch "cd('/Users/onion/Desktop/code/Contrast'); addpath('scheme1/matlab'); validate_ce1_hw_against_python();"`

Expected:
- Python tests all green
- MATLAB 校验正常结束
