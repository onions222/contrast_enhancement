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
    hist = [0] * cfg.n_bins
    shift = (cfg.input_max + 1).bit_length() - 1
    bin_shift = shift - cfg.n_bins.bit_length() + 1
    for sample in samples:
        clipped = min(max(sample, 0), cfg.input_max)
        index = clipped >> bin_shift
        hist[index] += 1
    return hist


def clip_and_redistribute(hist: Iterable[int], clip_limit: int) -> list[int]:
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
    clamped: list[int] = []
    prev = 0
    for value in values:
        bounded = min(max(value, 0), value_max)
        prev = max(prev, bounded)
        clamped.append(prev)
    return clamped


def estimate_histogram_mean(hist: Iterable[int], cfg: ContrastConfig) -> float:
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
        self.cfg = cfg or ContrastConfig()
        self.prev_lut: list[int] | None = None

    def process_frame(self, samples: Iterable[int]) -> FrameResult:
        sample_list = list(samples)
        hist = compute_histogram(sample_list, self.cfg)
        lut = generate_lut_from_histogram(hist, len(sample_list), self.prev_lut, self.cfg)
        mapped = [lut[min(max(sample, 0), self.cfg.input_max)] for sample in sample_list]
        self.prev_lut = lut
        return FrameResult(histogram=hist, lut=lut, mapped_samples=mapped)
