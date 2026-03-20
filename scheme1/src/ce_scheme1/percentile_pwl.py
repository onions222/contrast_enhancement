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
    pattern_bypass_enable: bool = True
    pattern_hist_bin_count: int = 32
    pattern_dense_active_min: int = 14
    pattern_dense_span_min: int = 16
    pattern_dense_runs_max: int = 2
    pattern_dense_holes_max: int = 2
    pattern_dense_flatness_numer: int = 3
    pattern_dense_flatness_denom: int = 4
    pattern_sparse_active_max: int = 6
    pattern_sparse_peak_numer: int = 2
    pattern_sparse_peak_denom: int = 5
    pattern_comb_span_min: int = 10
    pattern_comb_runs_min: int = 6
    pattern_comb_hole_numer: int = 1
    pattern_comb_hole_denom: int = 3


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

    def _normalize_value_samples(self, samples: Iterable[int]) -> list[int]:
        return [_normalize_to_8bit(sample, self.cfg.input_bit_depth) for sample in samples]

    def _pattern_histogram_features(self, value_samples: list[int]) -> dict[str, int]:
        values = np.array(value_samples, dtype=np.uint8)
        if values.size == 0:
            return {
                "active_bin_count": 0,
                "first_active_bin": 0,
                "last_active_bin": 0,
                "span_bin_count": 0,
                "active_run_count": 0,
                "longest_active_run": 0,
                "hole_count": 0,
                "sum_abs_diff": 0,
                "sum_active_count": 0,
                "max_bin_count": 0,
                "total_pixel_count": 0,
            }

        shift = 8 - int(np.log2(self.cfg.pattern_hist_bin_count))
        hist = np.bincount((values >> shift), minlength=self.cfg.pattern_hist_bin_count)
        active_mask = hist > 0
        active_indices = np.flatnonzero(active_mask)
        sum_abs_diff = int(np.abs(np.diff(hist.astype(np.int32))).sum())
        if active_indices.size == 0:
            return {
                "active_bin_count": 0,
                "first_active_bin": 0,
                "last_active_bin": 0,
                "span_bin_count": 0,
                "active_run_count": 0,
                "longest_active_run": 0,
                "hole_count": 0,
                "sum_abs_diff": sum_abs_diff,
                "sum_active_count": 0,
                "max_bin_count": 0,
                "total_pixel_count": int(values.size),
            }

        active_bin_count = int(active_mask.sum())
        first_active_bin = int(active_indices[0])
        last_active_bin = int(active_indices[-1])
        span_bin_count = last_active_bin - first_active_bin + 1
        hole_count = span_bin_count - active_bin_count

        active_run_count = 0
        longest_active_run = 0
        run = 0
        for is_active in active_mask.tolist():
            if is_active:
                run += 1
                if run == 1:
                    active_run_count += 1
                longest_active_run = max(longest_active_run, run)
            else:
                run = 0

        return {
            "active_bin_count": active_bin_count,
            "first_active_bin": first_active_bin,
            "last_active_bin": last_active_bin,
            "span_bin_count": int(span_bin_count),
            "active_run_count": int(active_run_count),
            "longest_active_run": int(longest_active_run),
            "hole_count": int(hole_count),
            "sum_abs_diff": int(sum_abs_diff),
            "sum_active_count": int(hist[active_mask].sum()),
            "max_bin_count": int(hist.max()),
            "total_pixel_count": int(values.size),
        }

    def _pattern_histogram_candidate(self, features: dict[str, int]) -> tuple[bool, str]:
        active_bin_count = features["active_bin_count"]
        span_bin_count = features["span_bin_count"]
        active_run_count = features["active_run_count"]
        hole_count = features["hole_count"]
        sum_abs_diff = features["sum_abs_diff"]
        sum_active_count = features["sum_active_count"]
        max_bin_count = features["max_bin_count"]
        total_pixel_count = features["total_pixel_count"]

        dense_gradient_candidate = (
            active_bin_count >= self.cfg.pattern_dense_active_min
            and span_bin_count >= self.cfg.pattern_dense_span_min
            and active_run_count <= self.cfg.pattern_dense_runs_max
            and hole_count <= self.cfg.pattern_dense_holes_max
            and sum_abs_diff * active_bin_count * self.cfg.pattern_dense_flatness_denom
            <= self.cfg.pattern_dense_flatness_numer * max(sum_active_count, 1)
        )
        if dense_gradient_candidate:
            return True, "dense_gradient"

        sparse_pattern_candidate = (
            active_bin_count <= self.cfg.pattern_sparse_active_max
            and max_bin_count * self.cfg.pattern_sparse_peak_denom <= total_pixel_count * self.cfg.pattern_sparse_peak_numer
        )
        if sparse_pattern_candidate:
            return True, "sparse_pattern"

        comb_candidate = (
            span_bin_count >= self.cfg.pattern_comb_span_min
            and hole_count * self.cfg.pattern_comb_hole_denom >= span_bin_count * self.cfg.pattern_comb_hole_numer
            and active_run_count >= self.cfg.pattern_comb_runs_min
            and max_bin_count < total_pixel_count
        )
        if comb_candidate:
            return True, "comb_pattern"

        return False, ""

    def _detect_pattern_bypass(self, value_samples: list[int]) -> dict[str, object]:
        if not self.cfg.pattern_bypass_enable:
            return {"pattern_bypass": False, "pattern_bypass_reason": ""}

        features = self._pattern_histogram_features(value_samples)
        bypass_active, bypass_reason = self._pattern_histogram_candidate(features)
        return {
            "pattern_bypass": bypass_active,
            "pattern_bypass_reason": bypass_reason,
            "pattern_features": features,
        }

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
                "pattern_bypass": False,
                "pattern_bypass_reason": "",
            },
        )

    def _build_frame_result(self, value_samples: list[int]) -> FloatPercentilePwlFrameResult:
        if not value_samples:
            return self._build_empty_result()

        hist = compute_histogram(value_samples, self.cfg)
        
        bypass_info = self._detect_pattern_bypass(value_samples)
        pattern_bypass = bypass_info["pattern_bypass"]
        
        full_hist = _build_full_histogram(value_samples, self.cfg.input_max)
        p_low = _percentile_from_histogram(full_hist, self.cfg.dark_percentile)
        p_high = _percentile_from_histogram(full_hist, self.cfg.bright_percentile)
        anchor_low, anchor_high, gain_nominal, gain = _resolve_anchor_span(p_low, p_high, self.cfg)
        knots = _build_centered_pwl_knots(anchor_low, anchor_high, self.cfg)
        curve = _expand_pwl_curve(knots, self.cfg)
        
        raw_lut = _monotonic_clamp([round(value) for value in curve], self.cfg.input_max)
        
        if pattern_bypass:
            raw_lut = list(range(self.cfg.lut_size))
            knots = ((0, 0.0), (self.cfg.input_max, float(self.cfg.input_max)))
            curve = [float(v) for v in raw_lut]

        lut = _smooth_lut(raw_lut, self.prev_lut, self.cfg)
        tone_curve = [float(value) for value in lut]
        mapped_samples = [lut[sample] for sample in value_samples]
        stats = {
            "p_low": p_low,
            "p_high": p_high,
            "anchor_low": anchor_low,
            "anchor_high": anchor_high,
            "gain_nominal": gain_nominal,
            "gain": gain,
            "output_low": float(self.cfg.toe_margin),
            "output_high": float(self.cfg.input_max) - float(self.cfg.shoulder_margin),
            "pattern_bypass": pattern_bypass,
            "pattern_bypass_reason": bypass_info["pattern_bypass_reason"],
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
        return self._build_frame_result(self._normalize_value_samples(samples))

    def process_plane_image(self, plane: np.ndarray) -> FloatPercentilePwlFrameResult:
        plane_u8 = np.asarray(plane, dtype=np.uint8)
        return self._build_frame_result(plane_u8.reshape(-1).tolist())
