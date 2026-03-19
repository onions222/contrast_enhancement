from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ce_scheme3.reference_model import (
    ContrastConfig,
    ContrastReferenceModel,
    FrameResult,
    _monotonic_clamp,
    compute_histogram,
    estimate_histogram_mean,
    generate_lut_from_histogram,
)
from ce_scheme3.discrete_scene_gain_int import (
    DiscreteSceneFrameResult,
    DiscreteSceneGainConfig,
    DiscreteSceneGainModel,
    DiscreteSceneRgbResult,
)


@dataclass(frozen=True)
class AdaptiveGammaConfig(ContrastConfig):
    gamma_gain: float = 0.7
    gamma_min: float = 0.65
    gamma_max: float = 1.35
    gamma_blend: float = 0.6


def _blend_with_previous_lut(lut: list[int], prev_lut: list[int] | None, cfg: ContrastConfig) -> list[int]:
    """把当前 LUT 与上一帧 LUT 按参考模型相同的时域系数做融合。"""
    if prev_lut is None:
        return lut
    blended = [
        ((cfg.alpha_den - cfg.alpha_num) * old + cfg.alpha_num * new) // cfg.alpha_den
        for old, new in zip(prev_lut, lut)
    ]
    return _monotonic_clamp(blended, cfg.input_max)


def generate_adaptive_gamma_lut_from_histogram(
    hist: Iterable[int],
    total_pixels: int,
    prev_lut: list[int] | None,
    cfg: AdaptiveGammaConfig,
) -> list[int]:
    """在基线直方图均衡 LUT 上叠加自适应 gamma 曲线。

    先复用参考模型生成基础 LUT，再由直方图均值估计当前帧亮度，推导 gamma
    系数，并把 gamma 曲线与基线 LUT 按 `gamma_blend` 混合，最后执行时域
    融合，得到更偏向亮度自适应的输出映射。
    """
    baseline_lut = generate_lut_from_histogram(hist, total_pixels, None, cfg)
    if total_pixels <= 0:
        return _blend_with_previous_lut(baseline_lut, prev_lut, cfg)

    mean_value = estimate_histogram_mean(hist, cfg)
    mean_norm = mean_value / max(cfg.input_max, 1)
    gamma = 1.0 - cfg.gamma_gain * (0.5 - mean_norm) * 2.0
    gamma = max(cfg.gamma_min, min(cfg.gamma_max, gamma))

    gamma_curve: list[int] = []
    for level in range(cfg.lut_size):
        norm = level / max(cfg.lut_size - 1, 1)
        mapped = int(round((norm**gamma) * cfg.input_max))
        gamma_curve.append(mapped)

    blended = []
    blend_weight = max(0.0, min(1.0, cfg.gamma_blend))
    for base_value in baseline_lut:
        gamma_value = gamma_curve[min(max(base_value, 0), cfg.input_max)]
        mixed = round((1.0 - blend_weight) * base_value + blend_weight * gamma_value)
        blended.append(mixed)

    blended = _monotonic_clamp(blended, cfg.input_max)
    return _blend_with_previous_lut(blended, prev_lut, cfg)


class AdaptiveGammaReferenceModel(ContrastReferenceModel):
    def __init__(self, cfg: AdaptiveGammaConfig | None = None) -> None:
        """初始化带自适应 gamma 的参考模型。"""
        super().__init__(cfg or AdaptiveGammaConfig())
        self.cfg = cfg or AdaptiveGammaConfig()

    def process_frame(self, samples: Iterable[int]) -> FrameResult:
        """处理单帧灰度样本，并使用自适应 gamma LUT 进行映射。"""
        sample_list = list(samples)
        hist = compute_histogram(sample_list, self.cfg)
        lut = generate_adaptive_gamma_lut_from_histogram(hist, len(sample_list), self.prev_lut, self.cfg)
        mapped = [lut[min(max(sample, 0), self.cfg.input_max)] for sample in sample_list]
        self.prev_lut = lut
        return FrameResult(histogram=hist, lut=lut, mapped_samples=mapped)
