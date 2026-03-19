from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ContrastConfig:
    n_bins: int = 32
    lut_size: int = 256
    alpha_num: int = 1
    alpha_den: int = 8
    input_max: int = 255
    clip_gain: float = 2.0
    enable_bin_smoothing: bool = True
    dark_percentile: float = 2.0
    bright_percentile: float = 98.0
    shadow_boost: float = 0.0
    highlight_suppress: float = 0.0


@dataclass(frozen=True)
class FrameResult:
    histogram: list[int]
    lut: list[int]
    mapped_samples: list[int]


def compute_histogram(samples: Iterable[int], cfg: ContrastConfig) -> list[int]:
    """根据配置把输入灰度样本量化到直方图 bin 中。

    这里假设输入动态范围与 `cfg.input_max` 对齐，并通过右移把 8bit
    或同等范围的样本映射到 `cfg.n_bins` 个桶里。所有输入都会先裁剪，
    以避免负数或越界值污染统计结果。
    """
    hist = [0] * cfg.n_bins
    shift = (cfg.input_max + 1).bit_length() - 1
    bin_shift = shift - cfg.n_bins.bit_length() + 1
    for sample in samples:
        clipped = min(max(sample, 0), cfg.input_max)
        index = clipped >> bin_shift
        hist[index] += 1
    return hist


def clip_and_redistribute(hist: Iterable[int], clip_limit: int) -> list[int]:
    """执行 CLAHE 风格的裁剪与均匀回灌。

    先把每个 bin 裁到 `clip_limit`，累计多余计数，再把 excess 尽量平均地
    分配回所有 bin。这样可以抑制局部峰值过强导致的 LUT 失真。
    """
    clipped = []
    excess = 0
    for count in hist:
        kept = min(count, clip_limit)
        clipped.append(kept)
        excess += count - kept

    n_bins = len(clipped)
    q, r = divmod(excess, n_bins)
    redistributed = [count + q for count in clipped]
    for idx in range(r):
        redistributed[idx] += 1
    return redistributed


def smooth_histogram_bins(hist: Iterable[int]) -> list[int]:
    """对 bin 直方图做一维 1-2-1 平滑。

    首尾 bin 采用边界复制，中间 bin 使用 `(left + 2*center + right) / 4`
    的整数近似。该步骤用于减小统计噪声，让后续 CDF 更稳定。
    """
    values = list(hist)
    if len(values) < 2:
        return values[:]

    smoothed: list[int] = []
    last_index = len(values) - 1
    for idx, center in enumerate(values):
        left = values[idx - 1] if idx > 0 else values[0]
        right = values[idx + 1] if idx < last_index else values[last_index]
        smoothed.append((left + (center << 1) + right) >> 2)
    return smoothed


def _expand_bin_lut_to_full_range(bin_lut: list[int], cfg: ContrastConfig) -> list[int]:
    """把按 bin 生成的粗粒度 LUT 插值扩展到逐灰阶 LUT。

    `bin_lut` 的长度通常等于 `n_bins`，这里只在相邻 bin 的输出之间做线性
    插值，得到长度为 `lut_size` 的完整映射表，便于逐像素直接查表。
    """
    full_lut: list[int] = []
    for level in range(cfg.lut_size):
        left_bin = min((level * cfg.n_bins) // cfg.lut_size, cfg.n_bins - 1)
        next_bin = min(left_bin + 1, cfg.n_bins - 1)
        start = (left_bin * cfg.lut_size) // cfg.n_bins
        end = ((left_bin + 1) * cfg.lut_size) // cfg.n_bins
        span = max(end - start, 1)
        offset = min(max(level - start, 0), span)
        left = bin_lut[left_bin]
        right = bin_lut[next_bin]
        blended = left + ((right - left) * offset) // span
        full_lut.append(blended)
    return full_lut


def _monotonic_clamp(values: Iterable[int], value_max: int) -> list[int]:
    """把序列裁剪到合法范围，并强制为单调不减。

    LUT 若出现回退会破坏灰阶顺序，因此这里在裁剪到 `[0, value_max]`
    之后，再用前一项约束当前项，确保输出始终非递减。
    """
    clamped: list[int] = []
    prev = 0
    for value in values:
        bounded = min(max(value, 0), value_max)
        prev = max(prev, bounded)
        clamped.append(prev)
    return clamped


def estimate_histogram_mean(hist: Iterable[int], cfg: ContrastConfig) -> float:
    """用 bin 中心估计原始样本均值。

    该函数不依赖逐像素数据，而是直接基于直方图近似计算平均亮度，适合
    用在自适应 gamma 或场景分类等只需要粗统计量的路径中。
    """
    bins = list(hist)
    total = sum(bins)
    if total <= 0:
        return 0.0

    bin_width = (cfg.input_max + 1) / cfg.n_bins
    weighted_sum = 0.0
    for index, count in enumerate(bins):
        center = min(cfg.input_max, (index + 0.5) * bin_width)
        weighted_sum += center * count
    return weighted_sum / total


def _apply_endpoint_protection(lut: list[int], cfg: ContrastConfig) -> list[int]:
    """在 LUT 两端施加可配置的阴影提升和高光抑制。

    阴影端根据 `shadow_boost` 在低灰区域附加正向偏置，高光端根据
    `highlight_suppress` 在高灰区域减小输出。处理后再次做单调约束。
    """
    if cfg.shadow_boost <= 0.0 and cfg.highlight_suppress <= 0.0:
        return lut

    protected: list[int] = []
    lut_max_index = max(cfg.lut_size - 1, 1)
    shadow_scale = cfg.input_max * 0.25
    highlight_scale = cfg.input_max * 0.20
    for index, value in enumerate(lut):
        norm = index / lut_max_index
        shadow_weight = max(0.0, 1.0 - 2.0 * norm)
        highlight_weight = max(0.0, 2.0 * norm - 1.0)
        adjusted = value
        adjusted += int(round(cfg.shadow_boost * shadow_weight * shadow_scale))
        adjusted -= int(round(cfg.highlight_suppress * highlight_weight * highlight_scale))
        protected.append(adjusted)
    return _monotonic_clamp(protected, cfg.input_max)


def generate_lut_from_histogram(
    hist: Iterable[int],
    total_pixels: int,
    prev_lut: list[int] | None,
    cfg: ContrastConfig,
) -> list[int]:
    """从直方图生成时域平滑后的对比度增强 LUT。

    流程包括：可选 bin 平滑、按 clip gain 进行峰值裁剪并回灌、由累计分布
    生成 bin 级 LUT、扩展到全灰阶 LUT、端点保护，以及和上一帧 LUT 做
    IIR 式时间滤波。若输入为空，则回退到前一帧或恒等 LUT。
    """
    if total_pixels <= 0:
        if prev_lut is not None:
            return prev_lut[:]
        return list(range(cfg.lut_size))

    bins = list(hist)
    if cfg.enable_bin_smoothing:
        bins = smooth_histogram_bins(bins)

    clip_limit = max(1, int((total_pixels / cfg.n_bins) * cfg.clip_gain))
    bins = clip_and_redistribute(bins, clip_limit)

    running = 0
    bin_lut: list[int] = []
    for count in bins:
        running += count
        mapped = (running * cfg.input_max) // total_pixels
        bin_lut.append(mapped)

    lut = _expand_bin_lut_to_full_range(bin_lut, cfg)
    lut = _monotonic_clamp(lut, cfg.input_max)
    lut = _apply_endpoint_protection(lut, cfg)

    if prev_lut is not None:
        lut = [
            ((cfg.alpha_den - cfg.alpha_num) * old + cfg.alpha_num * new) // cfg.alpha_den
            for old, new in zip(prev_lut, lut)
        ]
        lut = _monotonic_clamp(lut, cfg.input_max)

    return lut


class ContrastReferenceModel:
    def __init__(self, cfg: ContrastConfig | None = None) -> None:
        """初始化参考模型，并保存上一帧 LUT 作为时域状态。"""
        self.cfg = cfg or ContrastConfig()
        self.prev_lut: list[int] | None = None

    def process_frame(self, samples: Iterable[int]) -> FrameResult:
        """处理单帧灰度样本，输出直方图、LUT 和映射后的像素。

        该接口是 Python golden 的主入口。它会更新内部 `prev_lut` 状态，
        因而同一个模型实例适合按视频帧顺序连续调用。
        """
        sample_list = list(samples)
        hist = compute_histogram(sample_list, self.cfg)
        lut = generate_lut_from_histogram(hist, len(sample_list), self.prev_lut, self.cfg)
        mapped = [lut[min(max(sample, 0), self.cfg.input_max)] for sample in sample_list]
        self.prev_lut = lut
        return FrameResult(histogram=hist, lut=lut, mapped_samples=mapped)
