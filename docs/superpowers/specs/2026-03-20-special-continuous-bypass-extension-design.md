# Special Continuous Bypass Extension Design

## Summary

本设计是 `scheme1` 现有 histogram topology bypass 的补充扩展，不替换主规则，也不改变前四条规则的语义。它的唯一目的，是在 `uniform_sparse / narrow_continuous_transition / disconnected_comb / continuous_artificial` 都未命中时，再补抓一小类“连续型但高度人工”的特殊测试图。

本扩展被明确设计为：

- 后置规则
- 可单独删除
- 删除后不影响前四条主规则的判断结果

目标图像集中在两类特殊 pattern：

- `ddic_circular_gradient`
- `ddic_gradient_with_stripes`

## Motivation

当前 topology bypass 已经覆盖了大多数人工 pattern，也能把真实自然图误判压到较低水平。但仍有两类特殊图会漏判：

1. `circular_gradient`
   - 直方图是单段连续分布
   - `A` 大，`R = 1`，`F` 大
   - 拓扑上很像自然宽分布

2. `gradient_with_stripes`
   - 同样属于单段连续宽分布
   - 但分布内部带有较规则的结构性起伏

这两类图说明，仅靠现有的：

- `A`
- `C`
- `R`
- `F`
- `Pmax`
- `extrema_count`

仍然不足以完全区分“连续型自然图”和“连续型特殊测试图”。

## Design Principles

### Principle 1: Do Not Pollute Main Rules

主规则仍保持：

1. `uniform_sparse`
2. `narrow_continuous_transition`
3. `disconnected_comb`
4. `continuous_artificial`

新规则只在以上四条都未命中时再判断。

### Principle 2: Prefer False Positive Risk Here Over Main Rule Drift

本扩展明确允许比主规则更激进，因为它只服务于极少数特殊图，且后续硬件综合时可以直接删掉。

### Principle 3: Use A Shape Feature, Not A Pure Threshold Retune

既然已经验证只调现有阈值无法同时满足：

- 灰阶过渡类图尽量全抓
- 自然图误判尽量低

那么本扩展必须引入新的形状特征，而不是继续只调 `Pmax` 或 `A/F` 阈值。

## Input And Output

### Input

- `histogram32[32]`
- `TotalPixels`
- 已有 topology features:
  - `A`
  - `C`
  - `R`
  - `F`
  - `Pmax`
- 新增 shape feature:
  - `extrema_count`
  - `edge_pair_count`

### Output

- `bypass_flag`
- `bypass_reason = special_continuous_artificial`

## New Shape Features

### Feature 1: Extrema Count

定义在活跃区内部的一维直方图序列上。

设活跃区 bin 计数为：

```text
H[k], k = first_active ... last_active
```

对内部位置 `k`，若：

```text
(H[k] > H[k-1] and H[k] >= H[k+1]) or
(H[k] >= H[k-1] and H[k] > H[k+1])
```

则记为局部峰值。  
若：

```text
(H[k] < H[k-1] and H[k] <= H[k+1]) or
(H[k] <= H[k-1] and H[k] < H[k+1])
```

则记为局部谷值。

`extrema_count` 为局部峰谷总数。

### Meaning

- 平滑 ramp / gradient 往往 `extrema_count` 很低
- 自然图宽分布通常会有更多局部起伏
- 因此它是连续型 pattern 与自然图之间的重要区分量

### Feature 2: Edge Pair Count

定义活跃区内部、相邻 bin 对中“至少有一端接近全局峰值”的对数。

设：

```text
PeakThreshold = ceil(Pmax / 2)
```

对每个相邻 bin 对 `(H[k], H[k+1])`，若：

```text
H[k] >= PeakThreshold or H[k+1] >= PeakThreshold
```

则该对记为一个 `edge pair`。

记总数为：

```text
edge_pair_count
```

### Meaning

这个特征不是在做几何边缘检测，而是在判断：

- 是否存在较多相邻 bin 对都落在“高计数区域附近”

对 `circular_gradient` 和 `gradient_with_stripes`，这类“高计数区沿活跃区形成较宽结构”的现象更明显；而自然宽分布虽然可能有峰，但通常不会在整段上呈现这样规整的“高平台邻接”。

## Rule Placement

新增规则是第五条：

```text
Rule 5: special_continuous_artificial
```

执行顺序固定为：

```text
1. uniform_sparse
2. narrow_continuous_transition
3. disconnected_comb
4. continuous_artificial
5. special_continuous_artificial
```

只有前四条全部未命中时，第五条才有机会生效。

## Rule Definition

推荐判断骨架：

```text
if R == 1
and A >= pattern_special_continuous_active_min
and F >= pattern_special_continuous_span_min
and extrema_count <= pattern_special_continuous_extrema_max
and edge_pair_count >= pattern_special_continuous_edge_pair_min
    -> bypass
```

推荐默认阈值：

```text
pattern_special_continuous_active_min = 24
pattern_special_continuous_span_min = 24
pattern_special_continuous_extrema_max = 1
pattern_special_continuous_edge_pair_min = 6
```

## Why This Rule Is Removable

它是可删的，原因有三点：

1. 触发顺序在最后  
   删除后不会改变前四条的命中顺序。

2. 依赖特征独立  
   即使删掉 `edge_pair_count` 和 `special_continuous_artificial`，主规则仍然可以只依赖既有 topology features。

3. 规则意图单一  
   它只服务于极少数特殊测试图，而不是主 bypass 架构的一部分。

## Testing Requirements

新增规则必须满足：

1. 命中：
   - `ddic_circular_gradient`
   - `ddic_gradient_with_stripes`

2. 不改变以下主规则样本的命中 reason：
   - `pure_black`
   - `gray_step_wedge_16`
   - `gradient_full_ramp`
   - `gradient_near_black_ramp`

3. 对当前真实自然照片集，不新增明显误判

## Non-Goals

本扩展不负责：

- 重新定义主 bypass 体系
- 取代 `continuous_artificial`
- 追求最小硬件成本

它只负责：在工程调试阶段，把两类特殊连续 pattern 先补抓住。
