# DDIC 对比度增强安全性测试分析

## 当前测试覆盖现状

### 已有测试图片类别

| 类别 | 已覆盖 | 示例 |
|---|---|---|
| 高调自然场景 | ✅ | [high_key_window](file:///Users/onion/Desktop/code/Contrast/scheme3/src/ce_scheme3/starter_test_images.py#101-115), [high_key_document](file:///Users/onion/Desktop/code/Contrast/scheme3/src/ce_scheme3/starter_test_images.py#117-127), [high_key_backlit_room](file:///Users/onion/Desktop/code/Contrast/scheme3/src/ce_scheme3/starter_test_images.py#129-137) |
| 正常场景 | ✅ | [normal_indoor_blocks](file:///Users/onion/Desktop/code/Contrast/scheme3/src/ce_scheme3/starter_test_images.py#139-146), [normal_landscape](file:///Users/onion/Desktop/code/Contrast/scheme3/src/ce_scheme3/starter_test_images.py#148-170) |
| 低调/暗场 | ✅ | [low_key_midgray_detail](file:///Users/onion/Desktop/code/Contrast/scheme3/src/ce_scheme3/starter_test_images.py#181-187), [low_key_noise_room](file:///Users/onion/Desktop/code/Contrast/scheme3/src/ce_scheme3/starter_test_images.py#199-205), [low_key_neon](file:///Users/onion/Desktop/code/Contrast/scheme3/src/ce_scheme3/starter_test_images.py#207-213) |
| 灰阶 ramp | ✅ | full / near_black / near_white ramp |
| 低动态范围 | ✅ | [low_dr_flat](file:///Users/onion/Desktop/code/Contrast/scheme3/src/ce_scheme3/starter_test_images.py#237-239), [low_dr_subtle_blocks](file:///Users/onion/Desktop/code/Contrast/scheme3/src/ce_scheme3/starter_test_images.py#241-246) |
| 双/三峰分布 | ✅ | `bimodal_split`, `trimodal_bands` |
| 肤色块 | ✅ | [skin_patch](file:///Users/onion/Desktop/code/Contrast/scheme3/src/ce_scheme3/starter_test_images.py#172-179) |
| Color bars | ✅ | EBU 75%, RGB primary, RGBCMYKW, gray/skin mix |
| 单通道 ramp | ✅ | R/G/B × 8/32/64/256 级 × 水平/垂直 |
| Checkerboard | ✅ | [patterns.py](file:///Users/onion/Desktop/code/Contrast/scheme3/tests/test_patterns.py) 中有 |
| UI 界面模拟 | ✅ | `text_ui_dark_menu`, `text_ui_light_page` |
| 暗底加噪 | ✅ | [noise_on_dark](file:///Users/onion/Desktop/code/Contrast/scheme3/src/ce_scheme3/patterns.py#21-34) |

### 已有 pattern bypass 覆盖（仅 scheme3）

- **Dense gradient**：连续 bin 占满、flatness 满足 → bypass ✅
- **Sparse pattern**：极少 active bin → bypass ✅
- **Comb pattern**：间隔交替 active/hole → bypass ✅

---

## 问题一：还需要补充哪些测试图片？

从 DDIC 安全性角度看，现有覆盖缺少以下**高风险**场景：

### 1. 纯色 / 极低 DR 边界图片 ⚠️ 优先级最高

**风险**：对比度增强算法对全黑/全白/纯色帧的处理如果不正确，在 DDIC 开机、关机、待机、息屏唤醒等场景会产生可见的闪烁或色块。

| 补充图片 | 描述 | 预期行为 |
|---|---|---|
| `pure_black` (R=G=B=0) | 全黑帧 | 必须 bypass，输出 = 输入 |
| `pure_white` (R=G=B=255) | 全白帧 | 必须 bypass，输出 = 输入 |
| `pure_gray_128` | 均匀中灰 | 必须 bypass |
| `near_black_uniform` (R=G=B=2) | 接近全黑但非零 | 必须 bypass，**且不能放大码值** |
| `near_white_uniform` (R=G=B=253) | 接近全白但非满 | 必须 bypass，**且不能压低码值** |
| `dc_offset_1` | 全帧 DR=1 的微差图 | 验证 bypass 阈值精确行为 |

### 2. 单一码值带极少异常点 ⚠️ 优先级高

**风险**：在 DDIC 实际场景中常见的"几乎纯色但有个别坏点/边框"情况。若算法因极端像素的动态范围触发增强，可能放大噪声。

| 补充图片 | 描述 |
|---|---|
| `flat_with_single_hot_pixel` | 全帧 128，中心 1 个像素 = 255 |
| `flat_with_single_dead_pixel` | 全帧 128，中心 1 个像素 = 0 |
| `flat_with_border_artifact` | 全帧 128，顶行/底行 = 0（模拟黑边） |
| `near_flat_with_sparse_noise` | 全帧 120±1，随机 0.1% 像素 = 200 |

### 3. 帧间过渡场景 ⚠️ 优先级高

**风险**：DDIC 最怕的就是帧间闪烁。需要验证 temporal hold / IIR 在极端过渡下的行为。

| 补充序列 | 描述 |
|---|---|
| `scene_cut_black_to_bright` | 全黑 → 亮场（5帧序列） |
| `scene_cut_bright_to_dark` | 亮场 → 全黑（5帧序列） |
| `oscillating_scene` | Normal/Dark/Normal/Dark 反复切换 |
| `slow_fade_in` | DR 从 0 渐增到 128 |
| `slow_fade_out` | DR 从 128 渐减到 0 |
| `bypass_boundary_oscillation` | DR 在 3↔5 之间反复跨越阈值 |

### 4. DDIC 特有工模/测试 Pattern ⚠️ 优先级高

**风险**：DDIC 工厂测试、来料检验、量产 OQC 会使用人工 pattern。如果算法"增强"了这些 pattern，会导致测试不通过或假 NG。

| 补充图片 | 描述 |
|---|---|
| `smpte_bars` | SMPTE 标准色条 |
| `vertical_stripe_bw` | 黑白交替竖条（1px 宽） |
| `horizontal_stripe_bw` | 黑白交替横条（1px 宽） |
| `dot_matrix` | 规则点阵图 |
| `cross_hatch` | 十字交叉网格 |
| `window_pattern` | 中心纯白方块 + 纯黑背景 |
| `reverse_window` | 中心纯黑方块 + 纯白背景 |
| `gray_step_wedge_16` | 16 级灰阶梯 |
| `gray_step_wedge_64` | 64 级灰阶梯 |
| `rgb_single_primary` | 纯红/纯绿/纯蓝全帧 |
| `flicker_test_pair` | 两帧交替：灰128 vs 灰130 |

### 5. Banding / 量化敏感区域

**风险**：定点 LUT 量化在低灰度区域可能产生 contour/banding，在高端 OLED DDIC 上尤为明显。

| 补充图片 | 描述 |
|---|---|
| `shallow_ramp_0_to_16` | 极暗区域浅 ramp |
| `shallow_ramp_240_to_255` | 极亮区域浅 ramp |
| `diagonal_ramp` | 45° 斜向渐变 |
| `circular_gradient` | 中心辐射渐变 |

### 6. Overflow / 溢出边界专项

| 补充图片 | 描述 |
|---|---|
| `max_code_all_channels` | R=G=B=255 |
| `gain_stress_dark_cluster` | 暗场中集中 level=1~3 的像素，用于测 gain LUT 在 `input→0` 附近是否溢出 |
| `alternating_0_255` | 逐像素 0/255 交替，压力测试 histogram 和 gain 极端分布 |

---

## 问题二：如何更高效地避开人工测试 Pattern？

### 当前状态

- **Scheme3** 已有 [_pattern_histogram_candidate](file:///Users/onion/Desktop/code/Contrast/scheme3/src/ce_scheme3/discrete_scene_gain_float.py#277-307) 三路检测：dense / sparse / comb
- **Scheme1** 完全没有 pattern bypass 机制 ← **主要盲区**

### 建议方案：分层防御策略

```text
Layer 1: histogram 特征检测（已有，可增强）
Layer 2: 空间特征预筛（新增）
Layer 3: bypass 白名单寄存器（硬件层补充）
```

#### Layer 1: 增强 histogram 特征检测

现有 scheme3 的 [_pattern_histogram_candidate](file:///Users/onion/Desktop/code/Contrast/scheme3/src/ce_scheme3/discrete_scene_gain_float.py#277-307) 已能覆盖主要场景，但建议补充：

1. **Step Pattern 检测**：直方图呈"梳齿但等间距、等计数"的特征
   - 条件：`active_bin_count <= N` 且 `max_bin / min_active_bin < R`（即各 active bin 计数接近相等）
   - 命中时 bypass
   - 这能捕获灰阶梯、色条等标准 pattern

2. **单 bin 峰值检测**（纯色/近纯色帧特化）
   - 条件：`max_bin_count / total_pixel_count >= 0.95`
   - 这种帧无论 DR 如何，都不应增强

3. **Scheme1 移植**：把 histogram 特征检测移植到 scheme1
   - scheme1 当前只靠 percentile anchor，如果 P2≈0 且 P98≈255（如 checkerboard），gain 会变 ≈1.0，**效果上基本安全**
   - 但建议仍显式加入 bypass 路径，让行为可控、可追溯

#### Layer 2: 空间特征预筛（可选增强）

histogram 检测的局限是**只看统计分布，不看空间结构**。某些自然图像可能"恰好"具有与 pattern 相似的直方图。增加空间特征可以减少误 bypass：

1. **行间一致性检测**
   - 算法：对比相邻行的像素差均值，如果 [mean(|row[i] - row[i+1]|) ≈ 0](file:///Users/onion/Desktop/code/Contrast/scheme1/src/ce_scheme1/reference_model.py#120-137) 或呈严格周期，标记为可疑
   - 这对横条、纯色、水平 ramp 有效

2. **列间一致性检测**
   - 同上逻辑转90°，覆盖竖条、垂直 ramp

3. **自相关周期检测**
   - 对亮度序列做自相关，如果在某个短周期处出现 >0.9 的峰值，说明是人工重复 pattern
   - 这对 checkerboard、dot matrix、cross-hatch 有效

> [!IMPORTANT]
> 空间检测在硬件上成本较高（需要 line buffer 或帧存取），建议仅在控制路径的帧级统计阶段做**粗判**，不进像素主路径。可以在帧扫描时顺便累积行差/列差统计。

#### Layer 3: 寄存器级 bypass 白名单

作为最后一道防线，建议在硬件中预留：

| 寄存器 | 功能 |
|---|---|
| `force_bypass` | 1-bit，外部强制 bypass 所有增强 |
| `bypass_on_low_dr_threshold` | 配置值，低 DR bypass 门限（已有） |
| `bypass_on_uniform_threshold` | 配置值，当最大 bin 计数超过总像素 N% 时 bypass |
| `pattern_bypass_enable` | 1-bit，总开关（scheme3 已有） |

这样即使算法检测遗漏，DDIC 端的 firmware 或 bring-up 团队也可以通过寄存器手动关闭增强。

### 两个方案的优先级建议

| 措施 | Scheme1 现状 | Scheme3 现状 | 建议优先级 |
|---|---|---|---|
| 低 DR bypass | ✅ 隐式（anchor 收缩） | ✅ 显式 | —— |
| Histogram pattern bypass | ❌ 无 | ✅ 三路 | **scheme1 需移植** |
| 纯色单 bin bypass | ❌ 无 | ❌ 无（靠低 DR bypass） | 两者均建议加 |
| Step pattern 检测 | ❌ | ❌ | 建议加到 scheme3 |
| 空间特征检测 | ❌ | ❌ | 可选，硬件成本需评估 |
| force_bypass 寄存器 | 未知 | 未知 | **硬件上建议预留** |
| 补充测试 pattern 图片 | 部分缺失 | 部分缺失 | **立即补充** |

---

## 总结

1. **测试图片**：当前覆盖偏自然场景和基础 pattern，**缺少 DDIC 工模专用 pattern、极端边界值、帧间过渡序列、和 banding 敏感区域**的系统化测试
2. **Pattern bypass**：scheme3 的三路检测是好的起点，但**scheme1 完全缺失此机制**；两个方案都建议补充"纯色 / 单 bin 峰值 bypass"和"step pattern 检测"
3. **硬件级防御**：无论算法多智能，建议 DDIC 端预留 `force_bypass` 寄存器作为最终安全阀
