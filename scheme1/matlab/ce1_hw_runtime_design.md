# 方案一 MATLAB 定点运行时设计

## 文档定位

本文档面向数字 IC 设计、验证和 bring-up 团队。目标不是解释 MATLAB 写法，而是给出方案一控制路径和数据路径的硬件等效语义，包括：

- 输入输出接口
- 关键寄存器与位宽
- 帧级控制流程
- pattern bypass 判定链
- LUT 生成与时域收敛规则

## 算法目标

把方案一 `Percentile-Anchored PWL` 的算法，整理成适合数字 IC 交接的 MATLAB 定点版控制路径与数据路径。

方案一的主思路不是直接做 histogram equalization，而是：

1. 从整帧亮度分布里提取主体输入区间
2. 把这个输入区间映射到留有保护边界的输出区间
3. 用一条 5 点 PWL 曲线生成单调 `tone_lut`

这样做的优点是：

- 控制量少，容易调参
- 每一步都能明确解释为寄存器行为
- 像素侧只需查表，适合硬件
- 可以用 `gain_max`、`toe_margin`、`shoulder_margin` 显式保护风险场景

## 模块边界

### 控制路径输入

- `frame_in`
  - `U8.0` 或经位宽映射后的输入样本
- `cfg`
  - 控制寄存器镜像
- `prev_state`
  - 上一帧 LUT 和时域状态

### 控制路径输出

- `pattern_bypass_flag`
- `pattern_bypass_reason`
- `p_low / p_high`
- `gain_nominal_q8 / gain_q8`
- `anchor_low / anchor_high`
- `tone_lut`
- `state_out`

### 数据路径输入

- `input_u8`
- `tone_lut`

### 数据路径输出

- `mapped_frame`
- `mapped_samples`

## 数据格式

- 输入像素：`U8.0`
- 256-bin histogram counter：`Uceil(log2(Npix+1)).0`
- 32-bin histogram counter：`Uceil(log2(Npix+1)).0`
- `toe_margin` / `shoulder_margin`：`U8.0`
- `dark_percentile_q8` / `bright_percentile_q8`：`U7.8`
- `gain_min_q8` / `gain_max_q8`：`U4.8`
- `gain_nominal_q8` / `gain_q8`：`U4.8`
- `anchor_low` / `anchor_high` / `mid_x`：`U8.0`
- PWL 内部 `y`：`Q8`
- `tone_lut`：`256 x U8.0`

## 帧级处理流程

### Step 1. 输入归一化与 8bit 映射

**目的**

把所有输入统一到 `U8.0` 控制域，保证 histogram、anchor、LUT 都在固定地址空间内运行。

**处理方式**

- 默认输入已经满足接口位宽约束
- 大于 8bit 时右移
- 小于 8bit 时左移
- 对图像输入采用 `for row` + `for col` 双层循环逐像素处理，不使用矩阵化扫描

**公式**

```text
if input_bit_depth > 8:
    input_u8 = raw_sample >> (input_bit_depth - 8)
elseif input_bit_depth < 8:
    input_u8 = raw_sample << (8 - input_bit_depth)
else:
    input_u8 = raw_sample
```

### Step 2. 构建 256-bin 与 32-bin 直方图

**目的**

- `256-bin histogram` 用于精确 percentile 搜索
- `32-bin histogram` 用于粗分布输出

**处理方式**

- `histogram256` 直接按 `input_u8` 累加
- `histogram32` 按 `input_u8 >> 3` 累加
- 图像扫描顺序固定为行优先：外层 `row`，内层 `col`

**公式**

```text
histogram256[input_u8] = histogram256[input_u8] + 1
histogram32[input_u8 >> 3] = histogram32[input_u8 >> 3] + 1
```

### Step 2.5. Pattern bypass 预筛

**目的**

在真正进入 percentile anchor 搜索之前，先排除掉“本来就不应该做增强”的人工 pattern。

这里的核心判断不是“这张图能不能增强”，而是“这张图的码值关系是否应该被保持原样”。
对 DDIC 来说，很多测试图的任务是验证面板、Gamma、串扰、坏点、均匀性，而不是视觉观感优化。
因此一旦把这些图送进 CE 主路径，哪怕画面主观上没有明显变差，也可能破坏测试 pattern 本身的意义。

**输入**

- `histogram32`
- `total_pixels`
- `pattern_*` 系列寄存器

**处理方式**

- 只基于 32-bin 粗直方图做帧级判断
- 不引入空间卷积或局部窗口
- 先把 32-bin histogram 压缩成 32-bit `active mask`
- 再提取统一的拓扑特征：
  - `A`: 活跃 bin 数
  - `C`: 相邻活跃对数
  - `R = A - C`: 连续段数
  - `F`: 活跃跨度
  - `Pmax`: 最大单 bin 计数
- 最终规则分三层：
  - `uniform_sparse`
  - `disconnected_comb`
  - `continuous_artificial`
- 任一路命中则直接输出 `pattern_bypass_flag = 1`

**输出语义**

- `pattern_bypass_flag = 1`
  - 当前帧直接走 `identity_lut`
- `pattern_bypass_flag = 0`
  - 当前帧继续进入 percentile / gain / PWL 主路径

**工程效果**

- 命中 bypass 时，不再进入 percentile 搜索、gain 计算、anchor 扩展、PWL 生成
- 当前帧直接使用 `identity_lut`
- 但时域 IIR 仍然保留，用于减轻增强帧和 bypass 帧切换时的 LUT 跳变

**数学表达**

```text
mask[i] = 1, if histogram32[i] > (TotalPixels >> 10)
mask[i] = 0, otherwise

A = popcount(mask)
C = popcount(mask & (mask << 1))
R = A - C
F = last_active - first_active + 1
```

规则定义：

```text
Rule 1:
if A <= 2 -> bypass
reason = uniform_sparse

Rule 2:
if R * 4 > A -> bypass
reason = disconnected_comb

Rule 3:
if R == 1 and A >= 24 and F >= 24 and Pmax * 16 <= TotalPixels
    -> bypass
reason = continuous_artificial
```

**典型命中对象**

- `uniform_sparse`: pure color、near uniform、极低 DR 二级图
- `disconnected_comb`: color bars、step16、checker、stripe、comb-like pattern
- `continuous_artificial`: full ramp、smooth gradient、高级数 step wedge

**硬件映射**

- `mask generation`
  - 32 个比较器
- `A / C`
  - 2 次 popcount
- `R`
  - 1 次减法
- `F`
  - 首尾活跃索引差分
- `Pmax`
  - 32-bin max compare tree

### Step 3. 构造百分位目标并搜索 `p_low / p_high`

**目的**

找到主体内容的输入工作区间。percentile anchor 的意义是避免直接被极端暗点、极端高光、边缘黑边污染。

**处理方式**

- 百分位参数采用 `Q8`
- 真正搜索时使用交叉乘法比较，而不是先做除法
- `p_low` 使用从暗到亮的前向累计
- `p_high` 使用从亮到暗的反向 tail 扫描

**公式**

```text
low_target_numer  = total_pixels * dark_percentile_q8
high_target_numer = total_pixels * bright_percentile_q8
percent_den       = 100 * 256

running_count(level) = sum_{i=0..level} histogram256[i]
tail_count(level)    = sum_{i=level..255} histogram256[i]

p_low  = first level such that running_count(level) * percent_den >= low_target_numer
p_high = first level such that (total_pixels - tail_count(level)) * percent_den < high_target_numer
```

### Step 4. 计算输出工作区间

**目的**

给暗部和高光留出保护边界，不把内容直接映射满整个 `[0,255]``。`

**处理方式**

- `y_low` 由 `toe_margin` 决定
- `y_high` 由 `255 - shoulder_margin` 决定

**公式**

```text
y_low  = toe_margin
y_high = 255 - shoulder_margin
y_span = y_high - y_low
```

### Step 5. 计算 nominal gain

**目的**

估计主工作段所需斜率。这个量本质上就是“输入主体区间要被拉到输出工作区间，需要多强的增益”。

**处理方式**

- 先算输入主体宽度 `source_span`
- 再把 `y_span / source_span` 编成 `Q8`

**公式**

```text
source_span     = max(p_high - p_low, 1)
gain_nominal_q8 = floor((y_span * 256) / source_span)
```

含义：

- `source_span` 越小，`gain_nominal_q8` 越大
- `source_span` 越大，`gain_nominal_q8` 越接近 `1.0`

### Step 6. gain 限幅

**目的**

防止极窄动态范围输入导致过强增强，避免噪声放大、banding 和帧间抖动。

**公式**

```text
gain_q8 = clamp(gain_nominal_q8, gain_min_q8, gain_max_q8)
```

### Step 7. 确定最终 anchor span

**目的**

决定最终主增强段覆盖哪一段输入区间。

**处理方式**

1. 若 `gain_nominal_q8` 在允许范围内  
   直接使用 `p_low ~ p_high`
2. 若 `gain_nominal_q8` 超出允许范围  
   用目标 gain 反推所需跨度 `required_span`
   再围绕 percentile 中心扩展或收缩

**公式**

```text
if gain_min_q8 <= gain_nominal_q8 <= gain_max_q8:
    required_span = source_span
    anchor_low  = p_low
    anchor_high = p_high
else:
    required_span = ceil((y_span * 256) / gain_q8)
    center2 = p_low + p_high
    anchor_low  = floor((center2 - required_span) / 2)
    anchor_high = anchor_low + required_span
```

边界保护：

```text
if anchor_low < 0:
    anchor_high = anchor_high - anchor_low
    anchor_low = 0

if anchor_high > 255:
    anchor_low = anchor_low - (anchor_high - 255)
    anchor_high = 255
```

### Step 8. 构建 5 点 PWL

**目的**

把增强曲线压缩成少量 knot，便于硬件寄存器配置和线性插值生成 LUT。

**5 个点的意义**

- `(0, 0)`：固定起点
- `(x1, y1)`：主工作段左锚点
- `(mid_x, mid_y)`：中点，稳定中间调形状
- `(x3, y3)`：主工作段右锚点
- `(255, 255)`：固定终点

**公式**

```text
x0 = 0
y0 = 0
x1 = anchor_low
y1 = y_low
x3 = anchor_high
y3 = y_high
x4 = 255
y4 = 255
```

中点：

```text
mid_x = round_to_even((x1 + x3) / 2)
mid_y = (y1 + y3) / 2
```

说明：

- `mid_x` 最终落在 `U8.0`
- `mid_y` 在内部保持 `Q8`，这样能保留 `.5` 的语义

### Step 9. 从 PWL 生成 256 点 LUT

**目的**

把稀疏 knot 展开成逐灰度可查的 `tone_lut`。

**处理方式**

- 对每个 `level in [0,255]`
- 先判断它落在哪一段
- 再对该段做线性插值
- 插值内部使用 `Q8` 的 `y`
- 最终输出时做 `round_to_even`

**公式**

对任意线段 `(x0, y0)` 到 `(x1, y1)`：

```text
span = max(x1 - x0, 1)
dx   = level - x0
dy   = y1 - y0
y(level) = y0 + dy * dx / span
```

定点实现：

```text
interp_numer = y0_q8 * span + dy_q8 * dx
interp_code  = round_to_even(interp_numer / (span * 256))
```

### Step 10. 单调约束与端点保护

**目的**

保证 LUT 永远不回退，维持灰阶顺序。

**处理方式**

- 强制 `lut[0] = 0`
- 强制 `lut[255] = 255`
- 做一次 prefix max scan

**公式**

```text
lut[0]   = 0
lut[255] = 255

for i = 1..255:
    lut[i] = max(lut[i], lut[i-1])
```

### Step 11. temporal IIR

**目的**

抑制视频场景中 LUT 的帧间抖动。

**处理方式**

- 没有上一帧 LUT 时，直接输出 `raw_lut`
- 有上一帧 LUT 时，用整数 IIR 平滑
- 平滑后再次做单调约束

**公式**

```text
lut[i] = floor(((alpha_den - alpha_num) * prev_lut[i] + alpha_num * raw_lut[i]) / alpha_den)
```

### Step 12. 数据路径查表

**目的**

像素侧只做最简单的查表映射，把复杂逻辑全部留在控制路径。

**处理方式**

```text
mapped_pixel = tone_lut[input_pixel_u8]
```

图像侧同样采用双层循环：

```text
for row = 0 .. rows-1:
    for col = 0 .. cols-1:
        input_u8(row, col) = normalize_to_u8(frame_in(row, col))
        mapped_frame(row, col) = tone_lut[input_u8(row, col)]
```

这样做的目的，是让 MATLAB 行为和 RTL 的逐像素/逐拍处理方式直接对应，而不是依赖矩阵级批处理语义。

## rounding 规则

### 1. 普通下取整

```text
floor(a / b)
```

用于：

- `gain_nominal_q8`
- temporal IIR

### 2. banker's rounding / round-to-even

```text
round_to_even(z)
```

用于：

- `mid_x`
- PWL 展开后的 `tone_lut`

这样做的原因，是为了在 `.5` 情况下保持偶数舍入，避免整条曲线整体偏高 1 个码值。

## 空帧回退

当 `total_pixels == 0` 时：

- 若没有上一帧 LUT，则输出 identity LUT
- 若已有上一帧 LUT，则复用 `prev_lut`

这样能保证空帧、统计丢失或上层 flush 场景下仍然有稳定输出。

## 交付约束

- 核心路径不用浮点
- 核心路径不拆 helper
- 单调约束、边界保护和插值流程都在代码中显式表达
- 除法直接按算法公式书写，具体除法器结构不在 MATLAB 中展开
- 验证脚本只用于数值检查，不改变硬件主路径定义
