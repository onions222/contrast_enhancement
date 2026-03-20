# Histogram Topology Bypass Design

## Summary

本设计用于替代 `scheme1` 当前基于 `dense / sparse / comb` 三路规则的 pattern bypass。新的 bypass 架构以 `32-bin histogram` 的拓扑结构为核心，只保留极低成本的二值掩码、位计数和少量计数器，目标是在保持对人工 pattern 覆盖能力的同时，显著降低实现复杂度并提升规则可解释性。

核心思想是把 `32-bin histogram` 先压缩成 `32-bit active mask`，再从该掩码提取少量拓扑特征：

- `A`: 活跃 bin 数
- `C`: 相邻活跃对数
- `R = A - C`: 连续段数
- `F`: 活跃跨度
- `Pmax`: 最大单 bin 计数

其中 `A / C / R / F` 用于描述直方图的拓扑形状，`Pmax` 只作为连续型人工 pattern 的补充判据。

## Motivation

当前 bypass 的问题有两类：

1. 实现结构偏复杂  
   现有 `dense / sparse / comb` 三路需要组合使用 `active_bin_count`、`hole_count`、`run_count`、`sum_abs_diff`、`max_bin_count` 等多种特征，数据依赖较散，不利于硬件实现和调参。

2. 分类体系不统一  
   三路规则分别描述不同 pattern，但本质上都在尝试判断同一件事：直方图是“极简的、离散多段的，还是连续宽分布的”。规则命名和特征之间没有统一抽象。

新架构希望统一成“拓扑驱动”的判定方式。

## Input And Output

### Input

- `histogram32[32]`
  - `Uceil(log2(TotalPixels+1)).0`
  - 32-bin coarse histogram
- `TotalPixels`
  - `U32.0`
  - 当前帧总像素数

### Output

- `bypass_flag`
  - `1 bit`
- `bypass_reason`
  - 枚举值：
    - `uniform_sparse`
    - `disconnected_comb`
    - `continuous_artificial`
    - `none`

## Stage 1: Mask Generation

### Goal

把 32 个大位宽计数器压缩成一个只保留“该 bin 是否显著活跃”的 32-bit 拓扑描述。

### Rule

对每个 bin 执行：

```text
mask[i] = 1, if BinCount[i] > T_bin
mask[i] = 0, otherwise
```

推荐门限：

```text
T_bin = TotalPixels >> 10
```

即约 `0.1%` 像素占比。

### Hardware Mapping

- 32 个比较器
- 1 个右移器生成门限
- 32-bit 掩码寄存器

### Meaning

这一步的作用是剔除噪点、孤立异常像素和极小占比 bin，只保留“真正影响分布形状”的活跃区域。

## Stage 2: Topology Feature Extraction

### Feature 1: Active Count

```text
A = popcount(mask)
```

含义：

- 当前帧一共激活了多少个 coarse bin
- `A` 小说明分布很离散、很极简
- `A` 大说明分布覆盖范围较广

### Feature 2: Connectivity Count

```text
C = popcount(mask & (mask << 1))
```

含义：

- 有多少对相邻 bin 同时活跃
- `C` 大说明分布更连续
- `C` 小说明分布更离散

### Feature 3: Run Count

```text
R = A - C
```

数学原理：

若活跃分布由若干连续段组成，每段长度为 `L_k`，则：

```text
A = Σ L_k
C = Σ (L_k - 1)
```

因此：

```text
R = A - C
```

即连续段数量。

这是本设计最关键的等价关系，因为它允许只通过 `A` 和 `C` 推导 run 数，而不再单独扫描 active runs。

### Feature 4: Span

```text
F = last_active - first_active + 1
```

含义：

- 活跃分布在 32-bin 域中覆盖了多长的区间
- 用于区分“窄聚集分布”和“宽连续分布”

### Feature 5: Peak Count

```text
Pmax = max(BinCount[i])
```

含义：

- 最大单 bin 计数
- 主要用于最后一层连续型人工图判定

## Stage 3: Bypass Decision Hierarchy

新的 bypass 按拓扑形态划分为三类主规则。

### Rule 1: Uniform / Sparse

```text
if A <= 2 -> bypass
```

### Target

- pure black / white / gray
- near uniform
- 极低 DR 两级图
- 单块亮斑 / 暗块
- 单点缺陷类

### Reason

若只有 `1~2` 个活跃 bin，则该帧不具备值得 CE 增强的有效分布宽度。

### Rule 2: Disconnected / Comb

```text
if R * 4 > A -> bypass
```

等价地，也可以理解为：

```text
run_density = R / A
if run_density > 0.25 -> bypass
```

### Target

- color bars
- step wedge 低阶版本
- stripe / checker / dot matrix
- comb-like pattern
- alternating 0/255

### Reason

若 `R` 相对 `A` 过大，说明活跃 bin 被分裂成大量小段，分布呈离散条带或梳状结构。这种图的统计形态与自然图像差异明显，应直接 bypass。

### Rule 3: Continuous Artificial

拓扑触发条件：

```text
if R == 1 and A >= 24 and F >= 24
```

说明：

- `R == 1` 表示整个分布是一整段连续区间
- `A >= 24` 表示占用了绝大多数 coarse bins
- `F >= 24` 表示跨度也足够大，不是局部窄带

在满足以上条件后，再使用峰值均匀性判据：

```text
if Pmax * 16 <= TotalPixels -> bypass
```

也就是：

```text
Pmax / TotalPixels <= 1/16
```

### Target

- full ramp
- smooth gradient
- high-step wedge
- 某些连续型工模

### Reason

这类图的拓扑上看起来“非常自然”，因为它们是单段连续分布：

```text
A ≈ 32
C ≈ 31
R = 1
```

如果只看 `A/C/R/F`，它们会被放行。  
因此必须再补一个幅值相关量。这里使用 `Pmax`，因为连续型人工图通常更接近“近似均匀铺满”，单 bin 峰值不会很高。

## Recommended Final Logic

推荐的最终判定顺序：

```text
1. Generate mask
2. Compute A, C, R, F, Pmax
3. if A <= 2:
       bypass = 1
       reason = uniform_sparse
4. else if R * 4 > A:
       bypass = 1
       reason = disconnected_comb
5. else if R == 1 and A >= 24 and F >= 24 and Pmax * 16 <= TotalPixels:
       bypass = 1
       reason = continuous_artificial
6. else:
       bypass = 0
       reason = none
```

## Why This Replaces The Current Three-Branch Design

### Replaced Paths

- `sparse_pattern`
  - 由 `Rule 1` 覆盖
- `comb_pattern`
  - 由 `Rule 2` 覆盖
- `dense_gradient`
  - 由 `Rule 3` 覆盖

### Benefits

1. 特征统一  
   所有主判断都从同一份 `mask` 出发，避免当前三路分别依赖不同统计量。

2. 复杂度更低  
   主路径只需要：
   - 阈值比较
   - bitmask
   - 2 次 popcount
   - 首尾活跃索引
   - 最大 bin 计数

3. 可解释性更强  
   `A / C / R / F` 都对应清晰的拓扑概念，阈值含义直接。

## Risks And Validation Focus

### Risk 1: False Positive On Low-Complexity Natural Images

在 `HSV V` 域下，真实图像可能比 `Y` 域更稀疏，因此：

- `A` 可能更小
- `R/A` 可能更高

这会提高 `Rule 1` 和 `Rule 2` 的触发概率。

### Risk 2: Continuous Rule May Still Be Too Weak

`Rule 3` 当前只用 `Pmax` 做连续型 pattern 的补充判定。  
若后续发现 `full ramp` 与自然宽分布仍混淆，则需要补第二个连续型特征，例如轻量差分平滑度。

### Risk 3: Threshold Sensitivity

以下阈值都需要结合 starter dataset 做离线扫描：

- `T_bin`
- `A <= 2`
- `R * 4 > A`
- `A >= 24`
- `F >= 24`
- `Pmax * 16 <= TotalPixels`

## Validation Plan

实现前应先做离线统计，输出每张人工测试图的：

- `A`
- `C`
- `R`
- `F`
- `Pmax / TotalPixels`
- 命中规则

需要重点检查：

1. 是否覆盖现有人工图：
   - pure color
   - bars
   - checker / stripe / comb
   - ramp / gradient / step64

2. 是否误伤低复杂真实图：
   - dark scene
   - UI / text
   - high-key document
   - indoor blocks / landscape-like

3. 是否真的能替换当前三路 bypass，而不是只替换其中两路。

## Recommendation

推荐将该架构作为 `scheme1` bypass 的下一版候选主设计。  
理由：

- 它比当前三路 bypass 更统一
- 它的主特征完全适合 RTL
- 它能保留对离散 pattern 的强识别能力
- 只需增加一个轻量连续型判据，就有机会完整替代当前三路逻辑

不建议直接使用“只含 `A/C` 两个量的三条原始规则”上线，因为那样会放掉连续型人工 pattern。
