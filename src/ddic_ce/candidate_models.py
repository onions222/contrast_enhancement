from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ddic_ce.reference_model import (
    ContrastConfig,
    ContrastReferenceModel,
    FrameResult,
    _monotonic_clamp,
    compute_histogram,
    estimate_histogram_mean,
    generate_lut_from_histogram,
)


@dataclass(frozen=True)
class AdaptiveGammaConfig(ContrastConfig):
    gamma_gain: float = 0.7
    gamma_min: float = 0.65
    gamma_max: float = 1.35
    gamma_blend: float = 0.6


def _blend_with_previous_lut(lut: list[int], prev_lut: list[int] | None, cfg: ContrastConfig) -> list[int]:
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
        super().__init__(cfg or AdaptiveGammaConfig())
        self.cfg = cfg or AdaptiveGammaConfig()

    def process_frame(self, samples: Iterable[int]) -> FrameResult:
        sample_list = list(samples)
        hist = compute_histogram(sample_list, self.cfg)
        lut = generate_adaptive_gamma_lut_from_histogram(hist, len(sample_list), self.prev_lut, self.cfg)
        mapped = [lut[min(max(sample, 0), self.cfg.input_max)] for sample in sample_list]
        self.prev_lut = lut
        return FrameResult(histogram=hist, lut=lut, mapped_samples=mapped)


SCENE_NORMAL = 0
SCENE_BRIGHT = 1
SCENE_DARK_I = 2
SCENE_DARK_II = 3
SCENE_NAMES = {
    SCENE_NORMAL: "Normal",
    SCENE_BRIGHT: "Bright",
    SCENE_DARK_I: "Dark I",
    SCENE_DARK_II: "Dark II",
}


@dataclass(frozen=True)
class DiscreteSceneGainConfig(ContrastConfig):
    input_bit_depth: int = 8
    gain_frac_bits: int = 10
    gain_max: int = 1792
    bypass_dynamic_range_threshold: float = 4.0
    bright_mean_threshold: float = 168.0
    bright_ratio_threshold: float = 0.18
    dark2_mean_threshold: float = 56.0
    dark2_ratio_threshold: float = 0.80
    dark2_bright_ratio_threshold: float = 0.02
    dark1_mean_threshold: float = 104.0
    dark1_ratio_threshold: float = 0.50
    scene_cut_mean_delta: float = 32.0
    scene_switch_confirm_frames: int = 2
    scene_hold_enable: bool = True
    normal_strength: float = 0.50
    bright_strength: float = 0.65
    dark_i_strength: float = 0.70
    dark_ii_strength: float = 0.85
    family_m_knots: tuple[tuple[int, int], ...] = ((0, 0), (64, 40), (128, 128), (192, 224), (255, 255))
    family_b_knots: tuple[tuple[int, int], ...] = ((0, 0), (96, 72), (192, 208), (224, 246), (255, 255))
    family_d_knots: tuple[tuple[int, int], ...] = ((0, 0), (32, 12), (96, 128), (192, 236), (255, 255))


@dataclass(frozen=True)
class DiscreteSceneFrameResult(FrameResult):
    gain_lut: list[int]
    gain_samples: list[int]
    scene_id: int
    scene_name: str
    raw_scene_id: int
    raw_scene_name: str
    bypass_flag: bool
    stats: dict[str, float]


@dataclass(frozen=True)
class DiscreteSceneRgbResult(DiscreteSceneFrameResult):
    gain_mode_enabled: bool
    rgb_out: list[tuple[int, int, int]] | None


def _clip_to_bit_depth(value: int, bit_depth: int) -> int:
    value_max = (1 << bit_depth) - 1
    return min(max(int(value), 0), value_max)


def _normalize_to_luma_domain(value: int, bit_depth: int) -> int:
    clipped = _clip_to_bit_depth(value, bit_depth)
    if bit_depth == 8:
        return clipped
    if bit_depth > 8:
        return clipped >> (bit_depth - 8)
    return min(255, clipped << (8 - bit_depth))


def _rgb_to_luma8(rgb: Sequence[int], bit_depth: int) -> int:
    r = _normalize_to_luma_domain(int(rgb[0]), bit_depth)
    g = _normalize_to_luma_domain(int(rgb[1]), bit_depth)
    b = _normalize_to_luma_domain(int(rgb[2]), bit_depth)
    return min(255, (77 * r + 150 * g + 29 * b + 128) >> 8)


def _compute_percentile(sorted_samples: list[int], percentile: float) -> float:
    if not sorted_samples:
        return 0.0
    if len(sorted_samples) == 1:
        return float(sorted_samples[0])

    rank = (len(sorted_samples) - 1) * percentile / 100.0
    lower = int(rank)
    upper = min(lower + 1, len(sorted_samples) - 1)
    blend = rank - lower
    lower_value = float(sorted_samples[lower])
    upper_value = float(sorted_samples[upper])
    return lower_value + blend * (upper_value - lower_value)


def _summarize_luma_samples(samples: list[int]) -> dict[str, float]:
    if not samples:
        return {
            "mean": 0.0,
            "dark_ratio": 0.0,
            "bright_ratio": 0.0,
            "p2": 0.0,
            "p98": 0.0,
            "dynamic_range": 0.0,
            "min_luma": 0.0,
            "max_luma": 0.0,
        }

    total = len(samples)
    sorted_samples = sorted(samples)
    mean_value = float(sum(samples)) / total
    dark_ratio = float(sum(sample <= 63 for sample in samples)) / total
    bright_ratio = float(sum(sample >= 192 for sample in samples)) / total
    p2 = _compute_percentile(sorted_samples, 2.0)
    p98 = _compute_percentile(sorted_samples, 98.0)
    return {
        "mean": mean_value,
        "dark_ratio": dark_ratio,
        "bright_ratio": bright_ratio,
        "p2": p2,
        "p98": p98,
        "dynamic_range": p98 - p2,
        "min_luma": float(sorted_samples[0]),
        "max_luma": float(sorted_samples[-1]),
    }


def _generate_pwl_curve(knots: Sequence[tuple[int, int]], cfg: DiscreteSceneGainConfig) -> list[int]:
    curve: list[int] = []
    knot_list = sorted((min(max(x, 0), 255), min(max(y, 0), cfg.input_max)) for x, y in knots)
    for level in range(cfg.lut_size):
        if level <= knot_list[0][0]:
            curve.append(knot_list[0][1])
            continue
        if level >= knot_list[-1][0]:
            curve.append(knot_list[-1][1])
            continue

        for left, right in zip(knot_list, knot_list[1:]):
            x0, y0 = left
            x1, y1 = right
            if x0 <= level <= x1:
                span = max(x1 - x0, 1)
                offset = level - x0
                value = y0 + round((y1 - y0) * offset / span)
                curve.append(value)
                break
    return _monotonic_clamp(curve, cfg.input_max)


def _blend_identity_curve(curve: Sequence[int], strength: float, cfg: DiscreteSceneGainConfig) -> list[int]:
    blend = max(0.0, min(1.0, strength))
    values = []
    for level, target in enumerate(curve):
        mixed = round((1.0 - blend) * level + blend * target)
        values.append(mixed)
    return _monotonic_clamp(values, cfg.input_max)


def _tone_lut_to_gain_lut(tone_lut: Sequence[int], cfg: DiscreteSceneGainConfig) -> list[int]:
    gain_lut = [0]
    scale = 1 << cfg.gain_frac_bits
    for level in range(1, cfg.lut_size):
        gain = round((tone_lut[level] * scale) / level)
        gain_lut.append(min(max(gain, 0), cfg.gain_max))
    return gain_lut


def _identity_gain_lut(cfg: DiscreteSceneGainConfig) -> list[int]:
    identity_gain = 1 << cfg.gain_frac_bits
    return [0] + [identity_gain] * (cfg.lut_size - 1)


class DiscreteSceneGainModel:
    def __init__(self, cfg: DiscreteSceneGainConfig | None = None) -> None:
        self.cfg = cfg or DiscreteSceneGainConfig()
        self._scene_tone_luts = {
            SCENE_NORMAL: _blend_identity_curve(_generate_pwl_curve(self.cfg.family_m_knots, self.cfg), self.cfg.normal_strength, self.cfg),
            SCENE_BRIGHT: _blend_identity_curve(_generate_pwl_curve(self.cfg.family_b_knots, self.cfg), self.cfg.bright_strength, self.cfg),
            SCENE_DARK_I: _blend_identity_curve(_generate_pwl_curve(self.cfg.family_d_knots, self.cfg), self.cfg.dark_i_strength, self.cfg),
            SCENE_DARK_II: _blend_identity_curve(_generate_pwl_curve(self.cfg.family_m_knots, self.cfg), self.cfg.dark_ii_strength, self.cfg),
        }
        self._scene_gain_luts = {
            scene_id: _tone_lut_to_gain_lut(tone_lut, self.cfg)
            for scene_id, tone_lut in self._scene_tone_luts.items()
        }
        self._current_scene_id: int | None = None
        self._pending_scene_id: int | None = None
        self._pending_count = 0
        self._prev_mean: float | None = None

    def _classify_scene(self, stats: dict[str, float]) -> int:
        if stats["mean"] >= self.cfg.bright_mean_threshold and stats["bright_ratio"] >= self.cfg.bright_ratio_threshold:
            return SCENE_BRIGHT
        if (
            stats["mean"] <= self.cfg.dark2_mean_threshold
            and stats["dark_ratio"] >= self.cfg.dark2_ratio_threshold
            and stats["bright_ratio"] <= self.cfg.dark2_bright_ratio_threshold
        ):
            return SCENE_DARK_II
        if stats["mean"] <= self.cfg.dark1_mean_threshold and stats["dark_ratio"] >= self.cfg.dark1_ratio_threshold:
            return SCENE_DARK_I
        return SCENE_NORMAL

    def _select_scene(self, raw_scene_id: int, frame_mean: float) -> tuple[int, bool]:
        if self._current_scene_id is None:
            self._current_scene_id = raw_scene_id
            self._prev_mean = frame_mean
            return raw_scene_id, False

        scene_cut = self._prev_mean is not None and abs(frame_mean - self._prev_mean) >= self.cfg.scene_cut_mean_delta
        if not self.cfg.scene_hold_enable or scene_cut:
            self._current_scene_id = raw_scene_id
            self._pending_scene_id = None
            self._pending_count = 0
            self._prev_mean = frame_mean
            return raw_scene_id, scene_cut

        if raw_scene_id == self._current_scene_id:
            self._pending_scene_id = None
            self._pending_count = 0
            self._prev_mean = frame_mean
            return self._current_scene_id, False

        if self._pending_scene_id != raw_scene_id:
            self._pending_scene_id = raw_scene_id
            self._pending_count = 1
            self._prev_mean = frame_mean
            return self._current_scene_id, False

        self._pending_count += 1
        if self._pending_count >= max(self.cfg.scene_switch_confirm_frames, 1):
            self._current_scene_id = raw_scene_id
            self._pending_scene_id = None
            self._pending_count = 0
        self._prev_mean = frame_mean
        return self._current_scene_id, False

    def _normalize_luma_samples(self, samples: Iterable[int]) -> list[int]:
        return [_normalize_to_luma_domain(sample, self.cfg.input_bit_depth) for sample in samples]

    def _build_frame_result(self, luma_samples: list[int]) -> DiscreteSceneFrameResult:
        hist = compute_histogram(luma_samples, self.cfg)
        stats = _summarize_luma_samples(luma_samples)
        bypass_flag = stats["dynamic_range"] <= self.cfg.bypass_dynamic_range_threshold
        raw_scene_id = self._classify_scene(stats)
        scene_id, scene_cut = self._select_scene(raw_scene_id, stats["mean"])
        stats["scene_cut"] = float(scene_cut)

        if bypass_flag:
            tone_lut = list(range(self.cfg.lut_size))
            gain_lut = _identity_gain_lut(self.cfg)
        else:
            tone_lut = self._scene_tone_luts[scene_id]
            gain_lut = self._scene_gain_luts[scene_id]

        mapped_samples = [tone_lut[sample] for sample in luma_samples]
        gain_samples = [gain_lut[sample] for sample in luma_samples]
        return DiscreteSceneFrameResult(
            histogram=hist,
            lut=tone_lut,
            mapped_samples=mapped_samples,
            gain_lut=gain_lut,
            gain_samples=gain_samples,
            scene_id=scene_id,
            scene_name=SCENE_NAMES[scene_id],
            raw_scene_id=raw_scene_id,
            raw_scene_name=SCENE_NAMES[raw_scene_id],
            bypass_flag=bypass_flag,
            stats=stats,
        )

    def process_frame(self, samples: Iterable[int]) -> DiscreteSceneFrameResult:
        luma_samples = self._normalize_luma_samples(samples)
        return self._build_frame_result(luma_samples)

    def process_rgb_frame(
        self,
        rgb_samples: Iterable[Sequence[int]],
        *,
        cabc_enabled: bool,
        aie_enabled: bool,
    ) -> DiscreteSceneRgbResult:
        rgb_list = [
            tuple(_clip_to_bit_depth(int(channel), self.cfg.input_bit_depth) for channel in sample[:3])
            for sample in rgb_samples
        ]
        luma_samples = [_rgb_to_luma8(sample, self.cfg.input_bit_depth) for sample in rgb_list]
        frame_result = self._build_frame_result(luma_samples)
        gain_mode_enabled = cabc_enabled or aie_enabled
        rgb_out: list[tuple[int, int, int]] | None = None

        if not gain_mode_enabled:
            output_max = (1 << self.cfg.input_bit_depth) - 1
            rgb_out = []
            for pixel, gain in zip(rgb_list, frame_result.gain_samples):
                scaled = tuple(min(output_max, (channel * gain) >> self.cfg.gain_frac_bits) for channel in pixel)
                rgb_out.append(scaled)

        return DiscreteSceneRgbResult(
            histogram=frame_result.histogram,
            lut=frame_result.lut,
            mapped_samples=frame_result.mapped_samples,
            gain_lut=frame_result.gain_lut,
            gain_samples=frame_result.gain_samples,
            scene_id=frame_result.scene_id,
            scene_name=frame_result.scene_name,
            raw_scene_id=frame_result.raw_scene_id,
            raw_scene_name=frame_result.raw_scene_name,
            bypass_flag=frame_result.bypass_flag,
            stats=frame_result.stats,
            gain_mode_enabled=gain_mode_enabled,
            rgb_out=rgb_out,
        )
