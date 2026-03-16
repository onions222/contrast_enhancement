from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ddic_ce.reference_model import ContrastConfig, FrameResult, compute_histogram

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
class FloatDiscreteSceneGainConfig(ContrastConfig):
    input_bit_depth: int = 8
    gain_max: float = 1.75
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
class FloatDiscreteSceneFrameResult(FrameResult):
    tone_curve: list[float]
    gain_lut: list[float]
    gain_samples: list[float]
    scene_id: int
    scene_name: str
    raw_scene_id: int
    raw_scene_name: str
    bypass_flag: bool
    stats: dict[str, float]


@dataclass(frozen=True)
class FloatDiscreteSceneRgbResult(FloatDiscreteSceneFrameResult):
    gain_mode_enabled: bool
    rgb_out: list[tuple[float, float, float]] | None


def _clip_to_bit_depth(value: int, bit_depth: int) -> int:
    return min(max(int(value), 0), (1 << bit_depth) - 1)


def _normalize_to_8bit(value: int, bit_depth: int) -> int:
    clipped = _clip_to_bit_depth(value, bit_depth)
    if bit_depth == 8:
        return clipped
    if bit_depth > 8:
        return clipped >> (bit_depth - 8)
    return min(255, clipped << (8 - bit_depth))


def _rgb_to_luma8(rgb: Sequence[int], bit_depth: int) -> int:
    r = _normalize_to_8bit(int(rgb[0]), bit_depth)
    g = _normalize_to_8bit(int(rgb[1]), bit_depth)
    b = _normalize_to_8bit(int(rgb[2]), bit_depth)
    return min(255, (77 * r + 150 * g + 29 * b + 128) >> 8)


def _compute_percentile(sorted_samples: list[int], percentile: float) -> float:
    if not sorted_samples:
        return 0.0
    rank = (len(sorted_samples) - 1) * percentile / 100.0
    lower = int(rank)
    upper = min(lower + 1, len(sorted_samples) - 1)
    blend = rank - lower
    return float(sorted_samples[lower]) + blend * (float(sorted_samples[upper]) - float(sorted_samples[lower]))


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

    sorted_samples = sorted(samples)
    total = float(len(samples))
    p2 = _compute_percentile(sorted_samples, 2.0)
    p98 = _compute_percentile(sorted_samples, 98.0)
    return {
        "mean": sum(samples) / total,
        "dark_ratio": sum(sample <= 63 for sample in samples) / total,
        "bright_ratio": sum(sample >= 192 for sample in samples) / total,
        "p2": p2,
        "p98": p98,
        "dynamic_range": p98 - p2,
        "min_luma": float(sorted_samples[0]),
        "max_luma": float(sorted_samples[-1]),
    }


def _generate_pwl_curve(knots: Sequence[tuple[int, int]], cfg: FloatDiscreteSceneGainConfig) -> list[float]:
    points = sorted((min(max(x, 0), 255), float(min(max(y, 0), cfg.input_max))) for x, y in knots)
    curve: list[float] = []
    for level in range(cfg.lut_size):
        if level <= points[0][0]:
            curve.append(points[0][1])
            continue
        if level >= points[-1][0]:
            curve.append(points[-1][1])
            continue

        for left, right in zip(points, points[1:]):
            x0, y0 = left
            x1, y1 = right
            if x0 <= level <= x1:
                span = max(x1 - x0, 1)
                offset = level - x0
                curve.append(y0 + (y1 - y0) * offset / span)
                break
    return curve


def _blend_identity_curve(curve: Sequence[float], strength: float) -> list[float]:
    blend = max(0.0, min(1.0, strength))
    return [(1.0 - blend) * level + blend * target for level, target in enumerate(curve)]


def _tone_curve_to_gain_lut(tone_curve: Sequence[float], cfg: FloatDiscreteSceneGainConfig) -> list[float]:
    gain_lut = [0.0]
    for level in range(1, cfg.lut_size):
        gain_lut.append(min(max(tone_curve[level] / level, 0.0), cfg.gain_max))
    return gain_lut


def _identity_tone_curve(cfg: FloatDiscreteSceneGainConfig) -> list[float]:
    return [float(level) for level in range(cfg.lut_size)]


class FloatDiscreteSceneGainModel:
    def __init__(self, cfg: FloatDiscreteSceneGainConfig | None = None) -> None:
        self.cfg = cfg or FloatDiscreteSceneGainConfig()
        self._scene_tone_curves = {
            SCENE_NORMAL: _blend_identity_curve(_generate_pwl_curve(self.cfg.family_m_knots, self.cfg), self.cfg.normal_strength),
            SCENE_BRIGHT: _blend_identity_curve(_generate_pwl_curve(self.cfg.family_b_knots, self.cfg), self.cfg.bright_strength),
            SCENE_DARK_I: _blend_identity_curve(_generate_pwl_curve(self.cfg.family_d_knots, self.cfg), self.cfg.dark_i_strength),
            SCENE_DARK_II: _blend_identity_curve(_generate_pwl_curve(self.cfg.family_m_knots, self.cfg), self.cfg.dark_ii_strength),
        }
        self._scene_gain_luts = {
            scene_id: _tone_curve_to_gain_lut(tone_curve, self.cfg)
            for scene_id, tone_curve in self._scene_tone_curves.items()
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

    def _select_scene(self, raw_scene_id: int, frame_mean: float) -> int:
        if self._current_scene_id is None:
            self._current_scene_id = raw_scene_id
            self._prev_mean = frame_mean
            return raw_scene_id

        scene_cut = self._prev_mean is not None and abs(frame_mean - self._prev_mean) >= self.cfg.scene_cut_mean_delta
        if not self.cfg.scene_hold_enable or scene_cut:
            self._current_scene_id = raw_scene_id
            self._pending_scene_id = None
            self._pending_count = 0
            self._prev_mean = frame_mean
            return raw_scene_id

        if raw_scene_id == self._current_scene_id:
            self._pending_scene_id = None
            self._pending_count = 0
            self._prev_mean = frame_mean
            return self._current_scene_id

        if self._pending_scene_id != raw_scene_id:
            self._pending_scene_id = raw_scene_id
            self._pending_count = 1
            self._prev_mean = frame_mean
            return self._current_scene_id

        self._pending_count += 1
        if self._pending_count >= max(self.cfg.scene_switch_confirm_frames, 1):
            self._current_scene_id = raw_scene_id
            self._pending_scene_id = None
            self._pending_count = 0
        self._prev_mean = frame_mean
        return self._current_scene_id

    def _normalize_luma_samples(self, samples: Iterable[int]) -> list[int]:
        return [_normalize_to_8bit(sample, self.cfg.input_bit_depth) for sample in samples]

    def _build_frame_result(self, luma_samples: list[int]) -> FloatDiscreteSceneFrameResult:
        hist = compute_histogram(luma_samples, self.cfg)
        stats = _summarize_luma_samples(luma_samples)
        bypass_flag = stats["dynamic_range"] <= self.cfg.bypass_dynamic_range_threshold
        raw_scene_id = self._classify_scene(stats)
        scene_id = self._select_scene(raw_scene_id, stats["mean"])

        if bypass_flag:
            tone_curve = _identity_tone_curve(self.cfg)
            gain_lut = [0.0] + [1.0] * (self.cfg.lut_size - 1)
        else:
            tone_curve = self._scene_tone_curves[scene_id]
            gain_lut = self._scene_gain_luts[scene_id]

        lut = [round(value) for value in tone_curve]
        mapped_samples = [round(tone_curve[sample]) for sample in luma_samples]
        gain_samples = [gain_lut[sample] for sample in luma_samples]
        return FloatDiscreteSceneFrameResult(
            histogram=hist,
            lut=lut,
            mapped_samples=mapped_samples,
            tone_curve=tone_curve,
            gain_lut=gain_lut,
            gain_samples=gain_samples,
            scene_id=scene_id,
            scene_name=SCENE_NAMES[scene_id],
            raw_scene_id=raw_scene_id,
            raw_scene_name=SCENE_NAMES[raw_scene_id],
            bypass_flag=bypass_flag,
            stats=stats,
        )

    def process_frame(self, samples: Iterable[int]) -> FloatDiscreteSceneFrameResult:
        return self._build_frame_result(self._normalize_luma_samples(samples))

    def process_rgb_frame(
        self,
        rgb_samples: Iterable[Sequence[int]],
        *,
        cabc_enabled: bool,
        aie_enabled: bool,
    ) -> FloatDiscreteSceneRgbResult:
        rgb_list = [
            tuple(_clip_to_bit_depth(int(channel), self.cfg.input_bit_depth) for channel in sample[:3])
            for sample in rgb_samples
        ]
        luma_samples = [_rgb_to_luma8(sample, self.cfg.input_bit_depth) for sample in rgb_list]
        frame_result = self._build_frame_result(luma_samples)
        gain_mode_enabled = cabc_enabled or aie_enabled
        rgb_out: list[tuple[float, float, float]] | None = None

        if not gain_mode_enabled:
            output_max = float((1 << self.cfg.input_bit_depth) - 1)
            rgb_out = []
            for pixel, gain in zip(rgb_list, frame_result.gain_samples):
                scaled = tuple(min(output_max, channel * gain) for channel in pixel)
                rgb_out.append(scaled)

        return FloatDiscreteSceneRgbResult(
            histogram=frame_result.histogram,
            lut=frame_result.lut,
            mapped_samples=frame_result.mapped_samples,
            tone_curve=frame_result.tone_curve,
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
