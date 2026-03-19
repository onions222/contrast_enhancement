from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from ce_scheme1.reference_model import ContrastConfig, FrameResult, _monotonic_clamp, compute_histogram


@dataclass(frozen=True)
class FloatPercentilePwlConfig(ContrastConfig):
    input_bit_depth: int = 8
    gain_min: float = 0.5
    gain_max: float = 2.0
    toe_margin: float = 12.0
    shoulder_margin: float = 12.0
    enable_temporal_smoothing: bool = True


@dataclass(frozen=True)
class FloatPercentilePwlFrameResult(FrameResult):
    tone_curve: list[float]
    pwl_knots: tuple[tuple[int, float], ...]
    stats: dict[str, float]


def _clip_to_bit_depth(value: int, bit_depth: int) -> int:
    return min(max(int(value), 0), (1 << bit_depth) - 1)


def _normalize_to_8bit(value: int, bit_depth: int) -> int:
    clipped = _clip_to_bit_depth(value, bit_depth)
    if bit_depth == 8:
        return clipped
    if bit_depth > 8:
        return clipped >> (bit_depth - 8)
    return min(255, clipped << (8 - bit_depth))


def _build_full_histogram(samples: Sequence[int], value_max: int) -> list[int]:
    hist = [0] * (value_max + 1)
    for sample in samples:
        hist[min(max(int(sample), 0), value_max)] += 1
    return hist


def _percentile_from_histogram(hist: Sequence[int], percentile: float) -> float:
    total = sum(hist)
    if total <= 0:
        return 0.0
    threshold = max(0.0, min(1.0, percentile / 100.0)) * total
    running = 0
    for level, count in enumerate(hist):
        running += count
        if running >= threshold:
            return float(level)
    return float(len(hist) - 1)


def _shift_interval_to_domain(center: float, span: float, value_max: int) -> tuple[float, float]:
    span = max(1.0, min(span, float(value_max)))
    low = center - span / 2.0
    high = center + span / 2.0
    if low < 0.0:
        high -= low
        low = 0.0
    if high > value_max:
        low -= high - value_max
        high = float(value_max)
    low = max(0.0, low)
    high = min(float(value_max), high)
    return low, high


def _resolve_anchor_span(p_low: float, p_high: float, cfg: FloatPercentilePwlConfig) -> tuple[float, float, float, float]:
    y_low = float(cfg.toe_margin)
    y_high = float(cfg.input_max) - float(cfg.shoulder_margin)
    source_span = max(p_high - p_low, 1.0)
    gain_nominal = (y_high - y_low) / source_span
    target_gain = min(max(gain_nominal, cfg.gain_min), cfg.gain_max)
    required_span = max((y_high - y_low) / max(target_gain, 1e-6), 1.0)
    center = (p_low + p_high) / 2.0
    anchor_low, anchor_high = _shift_interval_to_domain(center, required_span, cfg.input_max)
    gain = (y_high - y_low) / max(anchor_high - anchor_low, 1.0)
    gain = min(max(gain, cfg.gain_min), cfg.gain_max)
    return anchor_low, anchor_high, gain_nominal, gain


def _build_centered_pwl_knots(
    anchor_low: float,
    anchor_high: float,
    cfg: FloatPercentilePwlConfig,
) -> tuple[tuple[int, float], ...]:
    x1 = int(round(min(max(anchor_low, 0.0), cfg.input_max)))
    x3 = int(round(min(max(anchor_high, 0.0), cfg.input_max)))
    if x3 < x1:
        x1, x3 = x3, x1
    mid_x = int(round((x1 + x3) / 2.0))
    y1 = float(cfg.toe_margin)
    y3 = float(cfg.input_max) - float(cfg.shoulder_margin)
    mid_y = (y1 + y3) / 2.0
    return (
        (0, 0.0),
        (x1, y1),
        (mid_x, mid_y),
        (x3, y3),
        (cfg.input_max, float(cfg.input_max)),
    )


def _expand_pwl_curve(
    knots: Sequence[tuple[int, float]],
    cfg: FloatPercentilePwlConfig,
) -> list[float]:
    ordered = sorted((min(max(int(x), 0), cfg.input_max), float(y)) for x, y in knots)
    curve: list[float] = []
    for level in range(cfg.lut_size):
        if level <= ordered[0][0]:
            curve.append(ordered[0][1])
            continue
        if level >= ordered[-1][0]:
            curve.append(ordered[-1][1])
            continue
        for left, right in zip(ordered, ordered[1:]):
            x0, y0 = left
            x1, y1 = right
            if x0 <= level <= x1:
                span = max(x1 - x0, 1)
                curve.append(y0 + (y1 - y0) * (level - x0) / span)
                break
    return curve


def _smooth_lut(lut: list[int], prev_lut: list[int] | None, cfg: FloatPercentilePwlConfig) -> list[int]:
    if not cfg.enable_temporal_smoothing or prev_lut is None:
        return lut
    blended = [
        ((cfg.alpha_den - cfg.alpha_num) * old + cfg.alpha_num * new) // cfg.alpha_den
        for old, new in zip(prev_lut, lut)
    ]
    return _monotonic_clamp(blended, cfg.input_max)


class FloatPercentilePwlModel:
    def __init__(self, cfg: FloatPercentilePwlConfig | None = None) -> None:
        self.cfg = cfg or FloatPercentilePwlConfig()
        self.prev_lut: list[int] | None = None

    def _normalize_luma_samples(self, samples: Iterable[int]) -> list[int]:
        return [_normalize_to_8bit(sample, self.cfg.input_bit_depth) for sample in samples]

    def _build_empty_result(self) -> FloatPercentilePwlFrameResult:
        lut = self.prev_lut[:] if self.prev_lut is not None else list(range(self.cfg.lut_size))
        return FloatPercentilePwlFrameResult(
            histogram=[0] * self.cfg.n_bins,
            lut=lut,
            mapped_samples=[],
            tone_curve=[float(value) for value in lut],
            pwl_knots=((0, 0.0), (self.cfg.input_max, float(self.cfg.input_max))),
            stats={
                "p_low": 0.0,
                "p_high": 0.0,
                "anchor_low": 0.0,
                "anchor_high": float(self.cfg.input_max),
                "gain_nominal": 1.0,
                "gain": 1.0,
            },
        )

    def _build_frame_result(self, luma_samples: list[int]) -> FloatPercentilePwlFrameResult:
        if not luma_samples:
            return self._build_empty_result()

        hist = compute_histogram(luma_samples, self.cfg)
        full_hist = _build_full_histogram(luma_samples, self.cfg.input_max)
        p_low = _percentile_from_histogram(full_hist, self.cfg.dark_percentile)
        p_high = _percentile_from_histogram(full_hist, self.cfg.bright_percentile)
        anchor_low, anchor_high, gain_nominal, gain = _resolve_anchor_span(p_low, p_high, self.cfg)
        knots = _build_centered_pwl_knots(anchor_low, anchor_high, self.cfg)
        curve = _expand_pwl_curve(knots, self.cfg)
        raw_lut = _monotonic_clamp([round(value) for value in curve], self.cfg.input_max)
        lut = _smooth_lut(raw_lut, self.prev_lut, self.cfg)
        tone_curve = [float(value) for value in lut]
        mapped_samples = [lut[sample] for sample in luma_samples]
        stats = {
            "p_low": p_low,
            "p_high": p_high,
            "anchor_low": anchor_low,
            "anchor_high": anchor_high,
            "gain_nominal": gain_nominal,
            "gain": gain,
            "output_low": float(self.cfg.toe_margin),
            "output_high": float(self.cfg.input_max) - float(self.cfg.shoulder_margin),
        }
        self.prev_lut = lut
        return FloatPercentilePwlFrameResult(
            histogram=hist,
            lut=lut,
            mapped_samples=mapped_samples,
            tone_curve=tone_curve,
            pwl_knots=knots,
            stats=stats,
        )

    def process_frame(self, samples: Iterable[int]) -> FloatPercentilePwlFrameResult:
        return self._build_frame_result(self._normalize_luma_samples(samples))

    def process_plane_image(self, plane: np.ndarray) -> FloatPercentilePwlFrameResult:
        plane_u8 = np.asarray(plane, dtype=np.uint8)
        return self._build_frame_result(plane_u8.reshape(-1).tolist())
