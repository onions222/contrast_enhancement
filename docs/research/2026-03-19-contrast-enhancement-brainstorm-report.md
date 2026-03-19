# 面向 DDIC/ISP 的 Contrast Enhancement Brainstorm Report

日期：`2026-03-19`

## 1. 目的

本报告用于把当前关于 `hardware-friendly contrast enhancement` 的 brainstorm 结果整理成一份可执行的技术报告。

本报告主要综合以下输入：

- [硬件友好对比度增强研究.md](/Users/onion/Desktop/code/Contrast/docs/research/硬件友好对比度增强研究.md)
- [2026-03-16-ddic-contrast-enhancement-research-notes.md](/Users/onion/Desktop/code/Contrast/docs/research/2026-03-16-ddic-contrast-enhancement-research-notes.md)
- [discrete_scene_gain_float.py](/Users/onion/Desktop/code/Contrast/scheme3/src/ce_scheme3/discrete_scene_gain_float.py)

写作目标不是立刻拍板唯一算法，而是：

- 把 8 个可思考的方案都保留下来
- 把每个方案写成接近实现说明书的形式
- 在报告后半部分明确指出 3 条最值得优先投入的路线

## 2. 统一假设

- 在线像素通路尽量保持为 `1x LUT / PWL tone curve + clamp`
- 允许逐帧统计
- 默认采用 `Frame N statistics -> Frame N+1 LUT`
- 默认避免全分辨率局部自适应处理
- 强烈偏好定点数/整数友好的控制逻辑
- 时域稳定性与静态图像质量同等重要

## 3. 统一符号

设：

- 输入亮度为 `x`，其中 `x in [0, L-1]`
- 输出亮度为 `y`
- 直方图为 `h(i)`
- 归一化直方图为

$$
p(i) = \frac{h(i)}{N}
$$

- 累积分布函数为

$$
C(i) = \sum_{k=0}^{i} p(k)
$$

- 百分位锚点为 `P_a`, `P_b`
- 最终 LUT 为 `T(i)`

若无特别说明，在线映射均可写为：

$$
y = T(x)
$$

或者其 PWL 近似形式。

## 4. 八个候选方案

### 4.1 方案一：Percentile-Anchored PWL Baseline

#### 核心思想

不使用原始 `min/max` 直接拉伸，而是使用稳健的百分位锚点，例如 `P2/P98` 或 `P3/P97`，再构造一条带 `toe` 和 `shoulder` 的单调 PWL 曲线。

这是最保守、最容易落地、最容易调参的基线方案。

#### 所需统计量

- `P_low`，例如 `P2` 或 `P3`
- `P_high`，例如 `P97` 或 `P98`
- `mean`
- 可选的 `dark_ratio`、`bright_ratio`

#### Step by Step

1. 统计当前帧的全局亮度直方图。
2. 根据 CDF 读出上下百分位锚点：

$$
P_a = \min \{ i \mid C(i) \ge a \}, \quad
P_b = \min \{ i \mid C(i) \ge b \}
$$

3. 计算有效动态范围：

$$
R = P_b - P_a
$$

4. 计算名义增益：

$$
g = \frac{L-1}{\max(R, 1)}
$$

5. 对增益做安全限制：

$$
g' = \min(\max(g, g_{\min}), g_{\max})
$$

6. 当 `g` 超过 `g_max` 时，向外扩展锚点区间，避免曲线斜率过大。
7. 根据锚点和目标强度，生成一组 PWL 控制点，例如：
   - `(0, 0)`
   - `(k1_x, k1_y)`，控制暗部抬升
   - `(mid_x, mid_y)`，控制中间调
   - `(k2_x, k2_y)`，控制高光 shoulder
   - `(L-1, L-1)`
8. 将控制点展开为单调 LUT。
9. 对锚点或最终 LUT 做时域平滑。
10. 写入 LUT 前强制单调并限制局部斜率。

#### 增益计算背后的数学动机

这一步的核心不是“为了算一个漂亮的数字”，而是为了确定 **PWL 中央主线段的目标斜率**。

如果我们希望把输入中的“有效亮度区间” `[P_a, P_b]` 映射到输出中的目标区间 `[Y_a, Y_b]`，那么中央线性段的理想斜率本质上就是：

$$
g_{\text{target}} = \frac{Y_b - Y_a}{P_b - P_a}
$$

最简单的情况，是**希望输入的有效区间几乎占满整个输出动态范围**，即：

$$
Y_a = 0, \quad Y_b = L-1
$$

于是就得到：

$$
g = \frac{L-1}{\max(P_b - P_a, 1)}
$$

这说明 `g` 其实是在回答一个非常直接的问题：

- 当前有效亮度区间有多宽？
- 如果要把它拉到目标输出范围，中央主段斜率应该多大？

如果还要预留 toe 和 shoulder 的缓冲区，则更一般的写法是：

$$
g = \frac{(L-1) - m_{\text{toe}} - m_{\text{shoulder}}}{\max(P_b - P_a, 1)}
$$

其中：

- `m_toe` 是给暗端软着陆预留的输出空间
- `m_shoulder` 是给亮端软着陆预留的输出空间

因此，`g` 不是单独存在的参数，它就是 PWL 中央线段的 slope 设计值。

#### 增益和 PWL 控制点的关系

一旦 `g` 确定，就可以直接用于构造 PWL 控制点。

最简单的 4 点形式可以写成：

- `(0, 0)`
- `(P_a, Y_a)`
- `(P_b, Y_b)`
- `(L-1, L-1)`

其中：

$$
Y_b = Y_a + g(P_b - P_a)
$$

如果引入 toe 和 shoulder，则可以写得更工程化一些：

$$
Y_a = m_{\text{toe}}
$$

$$
Y_b = (L-1) - m_{\text{shoulder}}
$$

$$
g = \frac{Y_b - Y_a}{\max(P_b - P_a, 1)}
$$

此时中间段实际上就是：

$$
y = Y_a + g(x - P_a), \quad x \in [P_a, P_b]
$$

然后在 `[0, P_a]` 与 `[P_b, L-1]` 两端分别补上 toe 和 shoulder 的过渡段。

换句话说：

- `P_a`, `P_b` 决定主线段落在输入轴上的位置
- `Y_a`, `Y_b` 决定主线段落在输出轴上的位置
- `g` 决定主线段的斜率

这三者共同确定了 PWL 曲线的中间主体。

#### 为什么值得保留

- 实现风险最低
- 和当前代码的 `P2/P98 + PWL curve` 思路最一致
- 非常适合做所有后续方案的对照基线

#### 主要风险

- 遇到多峰场景时可能不够聪明
- 百分位设得太激进时，可能牺牲主体暗部细节

### 4.2 方案二：Weighted Histogram as Policy, Not Direct LUT

#### 核心思想

不要让加权后的直方图直接生成最终 LUT，而是把“直方图变形”作为 `policy extractor`，提取出一些控制信号，再驱动更安全的 PWL 或 tone curve 生成器。

本质上是把 `histogram intelligence` 和 `curve generation` 解耦。

#### 所需统计量

- 原始直方图 `h(i)`
- 变形后的直方图 `w(i)`
- `mean`、`dark_ratio`、`bright_ratio`
- 可选的峰值、谷值、主峰宽度等形状描述子

#### Step by Step

1. 统计全局直方图。
2. 先做一次 clip：

$$
h_c(i) = \min(h(i), \tau_{\text{clip}})
$$

3. 视情况把 overflow 做均匀回灌或按规则回灌。
4. 对裁剪后的直方图施加权重函数：

$$
w(i) = f(h_c(i))
$$

典型形式可以是：

$$
w(i) = h_c(i)^\alpha, \quad 0 < \alpha < 1
$$

5. 从 `w(i)` 或其 CDF 中提取控制量，例如：
   - 暗部抬升强度
   - 中间调斜率
   - 高光压缩强度
6. 将这些控制量映射成 PWL 控制点或 tone-curve 参数。
7. 由这些参数生成单调 LUT。
8. 对控制参数和最终 LUT 做时域平滑。

#### 三个控制量的定义、获取方式与映射方法

这里建议显式定义三个控制量：

- 暗部抬升强度 `s_shadow`
- 中间调斜率 `s_mid`
- 高光压缩强度 `s_highlight`

先把加权后的直方图归一化：

$$
\hat{w}(i) = \frac{w(i)}{\sum_k w(k)}
$$

再定义其 CDF：

$$
C_w(i) = \sum_{k=0}^{i} \hat{w}(k)
$$

#### 1. 暗部抬升强度 `s_shadow`

暗部抬升最直接的量，就是暗部 weighted mass。设暗部阈值为 `t_d`，则：

$$
s_{\text{shadow}} = C_w(t_d)
$$

它反映的是：在加权后的统计分布中，有多少“重要权重”落在暗部。

- `s_shadow` 越大，说明暗部占比越高，越需要抬升
- `s_shadow` 越小，说明暗部不是主矛盾，不应强抬

#### 2. 中间调斜率 `s_mid`

中间调斜率可以通过 weighted inter-quantile span 来定义。先取加权分布的 25% 和 75% 分位：

$$
Q_{25}^w = \min \{ i \mid C_w(i) \ge 0.25 \}
$$

$$
Q_{75}^w = \min \{ i \mid C_w(i) \ge 0.75 \}
$$

定义中间调跨度：

$$
\Delta_{mid} = Q_{75}^w - Q_{25}^w
$$

再定义目标中间调斜率：

$$
s_{\text{mid}} = \operatorname{clip}\!\left(\frac{\kappa_{mid}}{\max(\Delta_{mid}, 1)}, s_{\min}, s_{\max}\right)
$$

其动机是：

- 如果加权分布在中间调非常集中，则 `Delta_mid` 小，说明中间调拥挤，需要更陡的主斜率
- 如果分布本来已经展开，则 `Delta_mid` 大，不需要再强行拉开

#### 3. 高光压缩强度 `s_highlight`

设高光阈值为 `t_b`，则高光 weighted mass 可定义为：

$$
s_{\text{highlight}} = 1 - C_w(t_b - 1)
$$

它反映的是：高亮端聚集了多少“重要权重”。

- `s_highlight` 越大，说明高光区域占比或权重越高，更需要 shoulder 压缩来保护高光层次
- `s_highlight` 越小，则高光保护可以更弱

#### 如何映射成 PWL 控制点

设主工作区间仍由 `P_a`, `P_b` 给出，并定义：

$$
x_1 = P_a, \quad x_2 = P_b, \quad x_m = \frac{P_a + P_b}{2}
$$

然后用三个控制量生成输出侧控制点：

暗部控制点：

$$
y_1 = P_a + \delta_{\text{shadow,max}} \cdot s_{\text{shadow}}
$$

中间调控制点：

$$
y_m = y_1 + s_{\text{mid}}(x_m - x_1)
$$

高光控制点：

$$
y_2 = (L-1) - \delta_{\text{highlight,max}} \cdot s_{\text{highlight}}
$$

最后约束：

$$
0 \le y_1 \le y_m \le y_2 \le L-1
$$

于是得到一组工程上很直接的控制点：

- `(0, 0)`
- `(x_1, y_1)`
- `(x_m, y_m)`
- `(x_2, y_2)`
- `(L-1, L-1)`

这部分映射不是某单篇论文的原式，而是更适合当前仓库的工程化落地方式：前半段用 histogram policy 提取趋势，后半段用 PWL 保证可控和可验证。

#### 为什么值得保留

- 比纯 HE 更可控
- 比直接 `weighted CDF -> LUT` 更稳
- 是 histogram 路线与 tone-curve 路线之间的桥

#### 主要风险

- 控制参数会变多
- 如果 policy 映射设计得不好，收益可能不如直接 PWL 明显

### 4.3 方案三：Adaptive WTHE as Strong Histogram Branch

#### 核心思想

把 `WTHE` 或类似的加权阈值直方图修改方法作为真正的 `hist -> CDF -> LUT` 分支，用于更强的全局自适应增强。

它适合作为强增强分支或比较分支，而不一定适合作为唯一默认基线。

#### 所需统计量

- 直方图 `h(i)`
- 上下阈值 `tau_low`, `tau_high`
- 可选的帧均值、方差，用于自适应调阈值

#### Step by Step

1. 统计全局直方图。
2. 根据帧级统计量决定 `tau_low` 和 `tau_high`。
3. 对**高频 bin 做裁剪**，对**过低 bin 做必要抬升**。
4. 对直方图做加权：

$$
w(i) =
\begin{cases}
\tau_{low}, & h(i) < \tau_{low} \\
h(i)^\alpha, & \tau_{low} \le h(i) \le \tau_{high} \\
\tau_{high}^\alpha, & h(i) > \tau_{high}
\end{cases}
$$

5. 归一化加权后的直方图：

$$
\hat{w}(i) = \frac{w(i)}{\sum_k w(k)}
$$

6. 构建加权 CDF：

$$
C_w(i) = \sum_{k=0}^{i} \hat{w}(k)
$$

7. 生成 LUT：

$$
T(i) = \lfloor (L-1) \cdot C_w(i) \rfloor
$$

8. 对 LUT 强制单调。
9. 对 LUT 的局部斜率做限制。
10. 对 `C_w` 或最终 LUT 做时域 IIR。

#### 强制单调的具体方法

最直接、最硬件友好的方法是 `prefix max scan`。

假设加权 CDF 生成的原始 LUT 为 `T_raw(i)`，则第一步先做裁剪：

$$
T_0(i) = \operatorname{clip}(T_{\text{raw}}(i), 0, L-1)
$$

然后做前向单调箝位：

$$
T_{\text{mono}}(0) = T_0(0)
$$

$$
T_{\text{mono}}(i) = \max(T_0(i), T_{\text{mono}}(i-1)), \quad i=1,\dots,L-1
$$

这意味着：如果某个位置因为量化误差、过强 weighting 或 rounding 导致比前一个点还小，就直接把它拉到前一个点的值。

如果还要限制局部斜率，可继续做第二步：

$$
T_{\text{cap}}(0) = T_{\text{mono}}(0)
$$

$$
T_{\text{cap}}(i) = \min(T_{\text{mono}}(i), T_{\text{cap}}(i-1) + s_{\max})
$$

这样就同时保证：

- 单调不减
- 相邻灰度级的最大增益受限

在硬件里，这两步都非常适合用简单的逐点扫描状态机实现。

#### 为什么值得保留

- 自适应能力强于单纯的 percentile stretch
- 仍然完全属于纯全局方案
- 可以最大限度复用 histogram 基础设施

#### 主要风险

- 对直方图形状变化仍然敏感
- 若 clipping/weighting 不稳，仍可能局部增益过高

### 4.4 方案四：Scene-Adaptive Curve Bank 2.0

#### 核心思想

不在每一帧重新解一条“最优曲线”，而是预先离线设计一个安全曲线库，再由帧统计驱动曲线选择或曲线混合。

这条路线最像真正的产品化架构。

#### 所需统计量

- `mean`
- `dark_ratio`
- `bright_ratio`
- `P2`、`P98`、`dynamic_range`
- 可选的直方图形状描述子

#### Step by Step

1. 离线准备一组安全曲线：
   - neutral
   - dark-scene lift
   - highlight protection
   - contrast boost
   - text/UI-safe
2. 在线统计当前帧的全局特征。
3. 用规则表、低维 LUT 或分段逻辑，将这些统计量映射成曲线权重。
4. 对权重做时域平滑。
5. 按点混合各条基底曲线：

$$
T(i) = \sum_{m=1}^{M} \lambda_m T_m(i), \quad \sum_m \lambda_m = 1
$$

6. 对混合后的 LUT 强制单调并限制斜率。
7. 必要时对特殊内容做旁路或弱化。

#### 硬件解释

- policy 侧负责生成 `lambda_m`
- 像素侧依旧只看到一条最终 LUT

#### 为什么值得保留

- 产品安全性高
- 可解释性强
- 和当前仓库里的 scene-based PWL 思路最接近

#### 主要风险

- 曲线库设计质量决定上限
- ~~如果只是硬切场景、不做 soft blend 和 hysteresis，会明显闪烁~~

### 4.5 方案五：Dark-Only AGCWD Branch

#### 核心思想

不要把 AGCWD 当成“全场景通用主线”，而是只在真正的暗场、低动态范围场景下开启它，把它做成专项增强分支。

这样可以保留 AGCWD 的优势，同时控制其代价和风险。

#### 所需统计量

- 直方图
- `pdf_min`、`pdf_max`
- `dark_ratio`、`bright_ratio`
- `mean`

#### Step by Step

1. 统计直方图并构造 PDF。
2. 判断是否进入 dark-only 分支，例如：

$$
\text{dark\_mode} =
(\text{mean} < \mu_d)
\land
(\text{dark\_ratio} > r_d)
\land
(\text{bright\_ratio} < r_b)
$$

3. 若不满足 dark mode，则退回其他分支。
4. 若满足 dark mode，则先对 PDF 做平滑或加权：

$$
p_w(i) = g(p(i))
$$

5. 构建修正后的 CDF：

$$
C_w(i) = \sum_{k=0}^{i} p_w(k)
$$

6. 把 CDF 转成逐灰度级 gamma 或等价 tone 参数：

$$
\gamma(i) = \phi(C_w(i))
$$

7. 根据 gamma 生成 LUT：

$$
T(i) = (L-1)\left( \frac{i}{L-1} \right)^{\gamma(i)}
$$

8. 将 LUT 定点化、限制斜率，并做时域平滑。

#### 灰度级 gamma 的原理

普通 gamma correction 使用的是固定幂律：

$$
T(x) = (L-1)\left(\frac{x}{L-1}\right)^\gamma
$$

其中：

- `gamma < 1` 时，暗部会被抬升
- `gamma > 1` 时，暗部会被压低

固定 gamma 的问题在于：它对整张图只给一个统一的幂律，无法反映当前直方图分布。

AGCWD 的核心思想是：

- 先从当前帧的 histogram 出发
- 通过加权和平滑得到一个“更适合增强”的分布
- 再让 `gamma` 随灰度级 `l` 变化，而不是全图只用一个常数

因此它本质上是在做：

$$
T(l) = (L-1)\left(\frac{l}{L-1}\right)^{\gamma(l)}
$$

也就是说，`gamma` 从“常数”变成了“随灰度级变化的函数”。

#### 计算过程

先定义原始 PDF：

$$
p(l) = \frac{n_l}{N}
$$

其中 `n_l` 是灰度级 `l` 的像素数。

然后取：

$$
p_{\min} = \min_l p(l), \quad p_{\max} = \max_l p(l)
$$

AGCWD 中一个常见的 weighted PDF 写法是：

$$
p_w(l) =
\begin{cases}
p_{\max}\left(\frac{p(l)-p_{\min}}{p_{\max}-p_{\min}}\right)^\alpha, & p_{\max} \ne p_{\min} \\
p(l), & p_{\max} = p_{\min}
\end{cases}
$$

这里：

- `alpha` 控制加权强度
- 加权的目的，是抑制过强峰值，得到更平滑、更可用的统计分布

然后对加权后的 PDF 重新归一化并积分：

$$
C_w(l) = \frac{\sum_{k=0}^{l} p_w(k)}{\sum_{k=0}^{L-1} p_w(k)}
$$

AGCWD 再用 weighted CDF 去定义逐灰度级 gamma。常见形式为：

$$
\gamma(l) = 1 - C_w(l)
$$

最后得到逐灰度级映射：

$$
T(l) = \operatorname{round}\left((L-1)\left(\frac{l}{L-1}\right)^{\gamma(l)}\right)
$$

#### 为什么能这么做

因为在最终实现里，在线像素通路并不需要真的“逐像素计算幂运算”。

控制侧只需要在 `V-blank` 或较低速域里，对所有 `l = 0,1,\dots,L-1` 预先算出 `T(l)`，再把它写成 1D LUT：

$$
T = \{T(0), T(1), \dots, T(L-1)\}
$$

于是像素侧仍然只是：

$$
y = T(x)
$$

换句话说：

- 数学上，它是“逐灰度级 gamma”
- 硬件上，它仍然是“单次查表”

这正是它可以用于 DDIC/ISP 的原因。

#### 为什么适合只放在 dark-only branch

AGCWD 的优势集中在：

- 暗场提亮
- 中间调柔和展开
- 比激进 HE 更自然的高光 roll-off

但它也带来：

- 定点近似复杂度
- gamma 量化误差
- banding 风险

因此，把它只限定在 `dark_ratio` 高、`bright_ratio` 低、`mean` 较低的场景中启用，比把它做成全场景默认主线更合理。

#### 为什么值得保留

- 对低照暗场非常有价值
- 相比激进 HE，高光行为通常更自然

#### 主要风险

- gamma 近似模块需要严格验证
- 如果精度不够，容易产生 banding

### 4.6 方案六：Brightness-Preserving Split Branch

#### 核心思想

当**“保持整体亮度氛围”比“追求强对比度”更重要**时，采用 `BBHE / DSIHE / MMBEBHE` 这类 split-histogram 路线。

它更适合作为曝光保真或氛围保真的专用分支。

#### 所需统计量

- 直方图
- 均值或中位数
- 可选的 `AMBE` 估计

#### Step by Step

1. 统计全局直方图。
2. 选择分割点：
   - `BBHE` 用均值
   - `DSIHE` 用中位数
   - `MMBEBHE` 用最小 `AMBE` 分割点
3. 将直方图切成左右两段：

$$
h_1(i), \quad i \le k
$$

$$
h_2(i), \quad i > k
$$

4. 分别归一化并计算两段 CDF。
5. 生成两条受各自定义域约束的子映射。
6. 将两段映射拼接成一条单调 LUT。
7. 对分割点或最终 LUT 做时域平滑。

#### MMBEBHE 的目标函数

可以写成：

$$
k^* = \arg\min_k \left| \mu_{out}(k) - \mu_{in} \right|
$$

其中 `mu_out(k)` 表示以 `k` 为分割点时理论输出均值。

#### MMBEBHE 的具体实现过程

MMBEBHE 的核心，不是简单地“按均值切一刀”，而是：

- 穷举所有候选分割点 `k`
- 对每个 `k` 构造双直方图均衡化输出
- 计算该输出的平均亮度
- 找到让输出平均亮度最接近输入平均亮度的那个 `k`

先定义输入平均亮度：

$$
\mu_{in} = \sum_{i=0}^{L-1} i \, p(i)
$$

对于任意候选分割点 `k`，先计算左右两部分概率质量：

$$
P_L(k) = \sum_{i=0}^{k} p(i), \quad
P_U(k) = 1 - P_L(k)
$$

然后分别定义左右子直方图的条件 CDF：

$$
C_L(i \mid k) = \frac{\sum_{j=0}^{i} p(j)}{P_L(k)}, \quad i \le k
$$

$$
C_U(i \mid k) = \frac{\sum_{j=k+1}^{i} p(j)}{P_U(k)}, \quad i > k
$$

接着定义左右两段映射：

$$
T_k(i) =
\begin{cases}
k \cdot C_L(i \mid k), & i \le k \\
(k+1) + (L-k-2)\cdot C_U(i \mid k), & i > k
\end{cases}
$$

这意味着：

- 左半部分只在 `[0, k]` 内重新分布
- 右半部分只在 `[k+1, L-1]` 内重新分布

因此它比普通 HE 更能保住整体亮度结构。

然后计算该分割点对应的理论输出均值：

$$
\mu_{out}(k) = \sum_{i=0}^{L-1} T_k(i)\, p(i)
$$

并计算绝对均值误差：

$$
AMBE(k) = |\mu_{out}(k) - \mu_{in}|
$$

最终选择：

$$
k^* = \arg\min_k AMBE(k)
$$

然后以 `k*` 对应的 `T_{k*}(i)` 作为最终 LUT。

#### 工程上的 Step by Step

1. 统计直方图 `h(i)`，归一化得到 `p(i)`。
2. 计算输入平均亮度 `mu_in`。
3. 枚举候选分割点 `k = 0,1,...,L-2`。
4. 对每个 `k`：
   - 计算 `P_L(k)` 和 `P_U(k)`
   - 计算左右 CDF
   - 生成候选 LUT `T_k(i)`
   - 计算 `mu_out(k)`
   - 计算 `AMBE(k)`
5. 选择 `AMBE(k)` 最小的 `k*`。
6. 输出 `T_{k*}`。
7. 对 `k*` 或最终 LUT 做时域平滑，避免分割点跳变。

#### 如何做得更硬件友好

理论上可以直接 brute-force 全扫 `k`，因为 8-bit 灰度下只有 256 个候选分割点。

更进一步的实现优化是：

- 预先构建前缀和 `H(i) = \sum_{j=0}^{i} h(j)`
- 再构建一阶矩前缀和 `M(i) = \sum_{j=0}^{i} j h(j)`

这样很多 `P_L(k)`、`P_U(k)` 以及均值相关量都能快速得到，不必每次重扫整个直方图。

因此，MMBEBHE 的工程现实性并不差，关键问题不在算力，而在：

- 分割点 `k*` 的时域稳定性
- 双段拼接后曲线转折点的平滑处理

#### 为什么值得保留

- 亮度保持能力强
- 对夜景、监控、曝光氛围敏感内容有意义

#### 主要风险

- 分割点 jitter 会导致时域不稳
- 拼接点若约束不足，曲线转折可能可见

### 4.7 方案七：Guard-Rail-First Architecture

#### 核心思想

把 guard rails 当成系统主架构的一部分，而不是“最后随便补几个保护开关”。

它虽然不是单独的 CE 核心算法，但它本身是一条重要的思考路线，因为很多量产失败并不是公式错了，而是缺护栏。

#### 所需统计量

- 任意核心算法需要的统计量
- 另外加上：
  - `dynamic_range`
  - dark-scene confidence
  - scene-cut confidence
  - 可选内容标志位

#### Step by Step

1. 先由某个核心 CE 分支生成候选 LUT。
2. 对 LUT 做单调箝位：

$$
T'(i) = \max(T(i), T'(i-1))
$$

3. 对 LUT 局部斜率做限制：

$$
T''(i) - T''(i-1) \le s_{\max}
$$

4. 在黑端和白端施加锚定保护，让曲线向 identity line 软着陆。
5. 当检测到极暗场时，减弱增强强度：

$$
T_{mix}(i) = (1-\alpha) i + \alpha T(i)
$$

其中 `alpha` 随暗噪风险增大而减小。

6. 若检测到 scene cut，则减弱或直接 reset 时域 IIR。
7. 若有内容保护标志位，则对选中内容做弱化或旁路。

#### 为什么值得保留

- 这是“demo 算法”变成“量产算法”的关键
- 绝大多数严重伪影都和 guard rails 缺失有关

#### 主要风险

- 护栏过多会把增强做平
- 必须明确主次，否则容易过度保守

### 4.8 方案八：Reserve Pseudo-Local Path

#### 核心思想

如果全局方法始终无法解决混合亮暗场景中的质量差距，可以引入极弱的伪局部信息，例如低分辨率 local mean map，再通过 2D-LUT 提供有限的局部适应能力。

这条路线明确属于 reserve path。

#### 所需统计量

- 像素亮度 `x`
- 降采样得到的局部均值 `m`
- 可选的全局场景模式

#### Step by Step

1. 对输入帧做大幅下采样，得到极低分辨率的 local illumination map。
2. 对于每个像素，通过插值恢复一个局部均值估计 `m`。
3. 用 `(x, m)` 作为 2D-LUT 的索引：

$$
y = T_{2D}(x, m)
$$

4. 局部维度保持很粗，避免 SRAM 和插值代价失控。
5. 必要时和全局分支结果混合：

$$
y = (1-\beta)T_g(x) + \beta T_{2D}(x, m)
$$

6. 严格限制这条路只在全局方法明显不够时使用。

#### 为什么值得保留

- 给纯全局方法留出一条升级通道
- 不用一上来就跳到全尺寸局部增强

#### 主要风险

- 强明暗边界容易出 halo
- 内存和验证成本会明显抬升

## 5. 最有价值的三条路线

这一部分不是说其余五条没价值，而是从下面几个维度综合排序后，最值得优先投入：

- 实现风险
- 硬件契合度
- 调参可解释性
- 验证成本
- 与当前仓库结构的兼容性

### 5.1 路线 A：Percentile + PWL + Guard Rails

#### 组成

这条路线由：

- 方案一作为核心映射
- 方案七作为必选护栏

构成。

#### 为什么有价值

- 它是最稳的基线。
- 当前仓库已经有 `P2/P98`、`dynamic_range`、PWL 曲线表示和 bypass 逻辑，这条路线与现有实现高度一致。
- 它能最快建立一个“可解释、可验证、可量化”的参考模型。
- 它天然符合 `stats -> PWL knots -> LUT` 的 handoff 方式。

#### Step by Step

1. 统计当前帧的直方图。
2. 读取百分位锚点 `P_a`, `P_b`。
3. 计算有效动态范围：

$$
R = P_b - P_a
$$

4. 计算中央主线段目标斜率：

$$
g = \frac{Y_b - Y_a}{\max(P_b - P_a, 1)}
$$

其中 `Y_a`, `Y_b` 是暗端/亮端预留保护后想映射到的输出坐标。

5. 生成 PWL 控制点：
   - `(0, 0)`
   - `(P_a, Y_a)`
   - `(P_b, Y_b)`
   - 必要时加入一个中间调点 `(x_m, y_m)`
   - `(L-1, L-1)`
6. 展开成 LUT。
7. 对 LUT 执行：
   - monotonic clamp
   - slope cap
   - endpoint anchoring
8. 对 LUT 或锚点做时域 IIR：

$$
T^{(t)}(i) = \rho T^{(t-1)}(i) + (1-\rho)T_{\text{new}}^{(t)}(i)
$$

9. 若检测到极暗场，则做强度混合：

$$
T_{mix}(i) = (1-\alpha)i + \alpha T(i)
$$

10. 输出最终 LUT。

#### 背后动机

这条路线的价值，不在于它“最聪明”，而在于它最容易把：

- 统计量
- 曲线
- 护栏
- 时域稳定性

四件事同时做清楚。

#### 预期收益

- 低工程风险
- 强时域可控性
- 非常利于后续和其他路线做 A/B 比较

### 5.2 路线 B：Weighted-Hist-Controlled Curve

#### 组成

这条路线以方案二为核心，可选地用方案三作为对照子分支。

关键不是“做不做 WTHE”，而是“WTHE 的信息到底直接控制 LUT，还是先转成 policy 再控制曲线”。

#### 为什么有价值

- 它是比纯 histogram baseline 更平衡的一条升级路线。
- 它能吸收 `WTHE` 的优点，但避免直接让加权 CDF 决定所有局部斜率。
- 它比路线 A 更自适应，但仍保留清晰的 policy layer。
- 它很适合作为路线 A 之后的主要增强分支。

#### Step by Step

1. 统计直方图 `h(i)`。
2. 对直方图做 clipping 与 weighting，得到 `w(i)`。
3. 归一化得到 `hat{w}(i)`，并构建 `C_w(i)`。
4. 从加权统计中提取三类控制量：

$$
s_{\text{shadow}} = C_w(t_d)
$$

$$
\Delta_{mid} = Q_{75}^w - Q_{25}^w
$$

$$
s_{\text{mid}} = \operatorname{clip}\!\left(\frac{\kappa_{mid}}{\max(\Delta_{mid},1)}, s_{\min}, s_{\max}\right)
$$

$$
s_{\text{highlight}} = 1 - C_w(t_b - 1)
$$

5. 把三类控制量映射成 PWL 控制点：

$$
y_1 = P_a + \delta_{\text{shadow,max}} s_{\text{shadow}}
$$

$$
y_m = y_1 + s_{\text{mid}}(x_m - x_1)
$$

$$
y_2 = (L-1) - \delta_{\text{highlight,max}} s_{\text{highlight}}
$$

6. 生成最终 PWL/LUT。
7. 对控制量和 LUT 同时做时域平滑。
8. 应用 monotonic clamp 与 slope cap。

#### 背后动机

路线 B 的关键是：

- 让 histogram 负责“看懂分布”
- 让 PWL 负责“安全地表达策略”

这样就避免了 raw WTHE 中“CDF 细节直接变成 LUT 细节”的不稳定问题。

#### 预期收益

- 中等复杂度
- 自适应能力明显强于纯 percentile stretch
- 比 raw WTHE 更容易纳入 guard rails

### 5.3 路线 C：Scene-Adaptive Blended Curve Bank

#### 组成

这条路线以方案四为核心，搭配方案七的 guard rails，并可吸收方案五的暗场专用思想。

#### 为什么有价值

- 这是最接近产品架构的一条路线。
- 它与当前代码最契合，因为现有实现已经包含 scene class、预设 curve family、hold 和 bypass。
- 它把 policy 和 mapping 清晰分离，特别适合工程调参和长期演进。
- 它也最适合未来扩展 skin/UI/pattern 等保护机制。

#### Step by Step

1. 离线准备一组基底曲线：
   - `T_normal`
   - `T_dark`
   - `T_bright_protect`
   - `T_contrast`
   - 可选 `T_ui_safe`
2. 在线统计特征向量：

$$
f = [\text{mean}, \text{dark\_ratio}, \text{bright\_ratio}, \text{dynamic\_range}]
$$

3. 根据 `f` 生成原始权重，例如：

$$
\tilde{\lambda}_{dark} = \operatorname{clip}\!\left(\frac{\text{dark\_ratio} - r_{d0}}{r_{d1} - r_{d0}}, 0, 1\right)
$$

$$
\tilde{\lambda}_{bright} = \operatorname{clip}\!\left(\frac{\text{bright\_ratio} - r_{b0}}{r_{b1} - r_{b0}}, 0, 1\right)
$$

$$
\tilde{\lambda}_{normal} = 1
$$

4. 归一化：

$$
\lambda_m = \frac{\tilde{\lambda}_m}{\sum_j \tilde{\lambda}_j}
$$

5. 对权重做时域 IIR 或 hysteresis。
6. 混合基底曲线：

$$
T(i) = \sum_{m=1}^{M} \lambda_m T_m(i)
$$

7. 对最终 LUT 施加 guard rails。
8. 必要时根据 pattern/UI/skin 标志位做弱化或旁路。

#### 背后动机

路线 C 的价值在于它把“增强决策”完全放在 policy 层，把“像素映射”完全放在 LUT 层。

这样做的好处是：

- 曲线是安全的、可人工校验的
- policy 可逐步迭代
- 最终硬件形态始终稳定

这也是它最像真实产品架构的原因。

#### 预期收益

- 最强的产品化潜力
- 与 `frame stats -> policy -> LUT` 的系统结构最一致
- 当 curve bank 设计得好时，安全性和画质上限都更高

## 6. 建议的推进顺序

1. 先实现路线 A，建立稳定基线。
2. 再做路线 B，形成最主要的算法增强分支。
3. 再把路线 C 演化成主产品化路线。
4. 方案五和方案六保留为特定目标场景下的专项分支。
5. 方案八严格放在最后，只作为保留通道。

## 7. 总结

这 8 个方案都值得保留，因为它们分别代表：

- 最稳的基线思路
- 更强的 histogram 变形思路
- 更像产品的 scene-policy 思路
- 暗场专项思路
- 亮度保真思路
- 系统护栏思路
- 以及超出纯全局方法后的 reserve 思路

但如果工程资源有限，最值得优先投入的仍然是：

1. `Percentile + PWL + Guard Rails`
2. `Weighted-Hist-Controlled Curve`
3. `Scene-Adaptive Blended Curve Bank`

这三条路线分别对应：

- 最安全的 baseline
- 最合理的自适应升级分支
- 最接近量产形态的长期主线

它们组合起来，可以覆盖当前阶段最重要的三件事：

- 先把稳定性做对
- 再把自适应能力做强
- 最后把产品化架构做稳

## 8. 本次补充中核实使用的关键资料

以下资料主要用于核实本次补充中涉及的公式、定义或算法原理：

1. Shih-Chia Huang, Fan-Chieh Cheng, Yi-Sheng Chiu, `Efficient contrast enhancement using adaptive gamma correction with weighting distribution`, IEEE Transactions on Image Processing, 2013, DOI: [10.1109/TIP.2012.2226047](https://doi.org/10.1109/TIP.2012.2226047)
2. S. D. Chen, A. R. Ramli, `Minimum mean brightness error bi-histogram equalization in contrast enhancement`, IEEE Transactions on Consumer Electronics, 2003, DOI: [10.1109/TCE.2003.1261234](https://doi.org/10.1109/TCE.2003.1261234)
3. S. D. Chen, A. R. Ramli, `Preserving brightness in histogram equalization based contrast enhancement techniques`, Digital Signal Processing, 2004, DOI: [10.1016/j.dsp.2004.04.001](https://doi.org/10.1016/j.dsp.2004.04.001)
4. Qing Wang, Robert K. Ward, `Fast Image/Video Contrast Enhancement Based on Weighted Thresholded Histogram Equalization`, IEEE Transactions on Consumer Electronics, 2007, DOI: [10.1109/TCE.2007.381756](https://doi.org/10.1109/TCE.2007.381756)
5. Tarik Arici, Salih Dikbas, Yucel Altunbasak, `A histogram modification framework and its application for image contrast enhancement`, IEEE Transactions on Image Processing, 2009, DOI: [10.1109/TIP.2009.2021548](https://doi.org/10.1109/TIP.2009.2021548)

说明：

- 方案二中“从 weighted histogram 提取 control signal，再映射到 PWL 控制点”的写法，属于结合上述资料与当前仓库结构得到的工程化扩展，不是某一篇论文的逐字原式。
- 路线 A/B/C 的展开也属于工程路线设计，不是对单篇论文的直接改写。
