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
    rgb_gain_blend: float = 0.25
    enable_temporal_smoothing: bool = True
    pattern_bypass_enable: bool = True
    pattern_hist_bin_count: int = 32
    pattern_active_threshold_shift: int = 10
    pattern_uniform_sparse_active_max: int = 2
    pattern_narrow_continuous_active_max: int = 8
    pattern_narrow_continuous_span_max: int = 8
    pattern_narrow_continuous_peak_denom: int = 2
    pattern_disconnected_comb_runs_mul: int = 4
    pattern_continuous_active_min: int = 24
    pattern_continuous_span_min: int = 24
    pattern_continuous_peak_denom: int = 16
    pattern_continuous_extrema_max: int = 1
    pattern_special_continuous_active_min: int = 24
    pattern_special_continuous_span_min: int = 24
    pattern_special_continuous_peak_denom: int = 12
    pattern_special_continuous_extrema_max: int = 1
    pattern_special_plateau_extrema_max: int = 3
    pattern_special_plateau_diff_max: int = 256
    pattern_special_plateau_pair_min: int = 28
    pattern_special_edge_pair_max: int = 2


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


def _build_anchor_pwl_knots(
    anchor_low: float,
    anchor_high: float,
    cfg: FloatPercentilePwlConfig,
) -> tuple[tuple[int, float], ...]:
    x1 = int(round(min(max(anchor_low, 0.0), cfg.input_max)))
    x3 = int(round(min(max(anchor_high, 0.0), cfg.input_max)))
    if x3 < x1:
        x1, x3 = x3, x1
    y1 = float(cfg.toe_margin)
    y3 = float(cfg.input_max) - float(cfg.shoulder_margin)
    return (
        (0, 0.0),
        (x1, y1),
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


def apply_value_output_to_rgb_image(
    rgb_image: np.ndarray,
    value_output: np.ndarray,
    rgb_gain_blend: float,
) -> np.ndarray:
    rgb_u8 = np.asarray(rgb_image, dtype=np.uint8)
    value_out = np.asarray(value_output, dtype=np.float32)
    value_in = rgb_u8.max(axis=2).astype(np.float32)
    gain = value_out / np.maximum(value_in, 1.0)
    blended_gain = 1.0 + float(rgb_gain_blend) * (gain - 1.0)
    out = np.clip(rgb_u8.astype(np.float32) * blended_gain[:, :, None], 0.0, 255.0)
    return np.rint(out).astype(np.uint8)


class FloatPercentilePwlModel:
    def __init__(self, cfg: FloatPercentilePwlConfig | None = None) -> None:
        self.cfg = cfg or FloatPercentilePwlConfig()
        self.prev_lut: list[int] | None = None

    def _normalize_value_samples(self, samples: Iterable[int]) -> list[int]:
        return [_normalize_to_8bit(sample, self.cfg.input_bit_depth) for sample in samples]

    def _topology_features_from_hist(self, hist: Sequence[int], total_pixels: int) -> dict[str, int]:
        if total_pixels <= 0:
            return {
                "active_count": 0,
                "connectivity_count": 0,
                "run_count": 0,
                "span_count": 0,
                "first_active_bin": 0,
                "last_active_bin": 0,
                "max_bin_count": 0,
                "extrema_count": 0,
                "edge_pair_count": 0,
                "plateau_pair_count": 0,
                "mask": 0,
                "threshold": 0,
                "total_pixel_count": 0,
            }

        threshold = max(total_pixels >> self.cfg.pattern_active_threshold_shift, 0)
        mask_bits = 0
        max_bin_count = 0
        for index, count in enumerate(hist):
            count_i = int(count)
            if count_i > threshold:
                mask_bits |= 1 << index
            if count_i > max_bin_count:
                max_bin_count = count_i

        active_count = mask_bits.bit_count()
        connectivity_count = (mask_bits & ((mask_bits << 1) & ((1 << self.cfg.pattern_hist_bin_count) - 1))).bit_count()
        run_count = active_count - connectivity_count

        if active_count > 0:
            first_active_bin = (mask_bits & -mask_bits).bit_length() - 1
            last_active_bin = mask_bits.bit_length() - 1
            span_count = last_active_bin - first_active_bin + 1
            active_hist = [int(hist[index]) for index in range(first_active_bin, last_active_bin + 1)]
        else:
            first_active_bin = 0
            last_active_bin = 0
            span_count = 0
            active_hist = []

        extrema_count = 0
        plateau_pair_count = 0
        edge_pair_count = 0
        peak_half_threshold = (max_bin_count + 1) // 2
        if active_hist:
            for left, right in zip(active_hist, active_hist[1:]):
                if abs(right - left) <= self.cfg.pattern_special_plateau_diff_max:
                    plateau_pair_count += 1
                if left >= peak_half_threshold or right >= peak_half_threshold:
                    edge_pair_count += 1
            for left, center, right in zip(active_hist, active_hist[1:], active_hist[2:]):
                if (
                    (center > left and center >= right)
                    or (center >= left and center > right)
                    or (center < left and center <= right)
                    or (center <= left and center < right)
                ):
                    extrema_count += 1

        return {
            "active_count": active_count,
            "connectivity_count": connectivity_count,
            "run_count": run_count,
            "span_count": span_count,
            "first_active_bin": first_active_bin,
            "last_active_bin": last_active_bin,
            "max_bin_count": max_bin_count,
            "extrema_count": extrema_count,
            "edge_pair_count": edge_pair_count,
            "plateau_pair_count": plateau_pair_count,
            "mask": mask_bits,
            "threshold": threshold,
            "total_pixel_count": int(total_pixels),
        }

    def _pattern_histogram_features(self, value_samples: list[int]) -> dict[str, int]:
        values = np.array(value_samples, dtype=np.uint8)
        if values.size == 0:
            return self._topology_features_from_hist([0] * self.cfg.pattern_hist_bin_count, total_pixels=0)

        shift = 8 - int(np.log2(self.cfg.pattern_hist_bin_count))
        hist = np.bincount((values >> shift), minlength=self.cfg.pattern_hist_bin_count)
        return self._topology_features_from_hist(hist.tolist(), total_pixels=int(values.size))

    def _pattern_histogram_candidate(self, features: dict[str, int]) -> tuple[bool, str]:
        active_count = features["active_count"]
        run_count = features["run_count"]
        span_count = features["span_count"]
        max_bin_count = features["max_bin_count"]
        extrema_count = features["extrema_count"]
        edge_pair_count = features["edge_pair_count"]
        plateau_pair_count = features["plateau_pair_count"]
        total_pixel_count = features["total_pixel_count"]

        if active_count <= self.cfg.pattern_uniform_sparse_active_max:
            return True, "uniform_sparse"

        if (
            run_count == 1
            and active_count <= self.cfg.pattern_narrow_continuous_active_max
            and span_count <= self.cfg.pattern_narrow_continuous_span_max
            and max_bin_count * self.cfg.pattern_narrow_continuous_peak_denom <= total_pixel_count
        ):
            return True, "narrow_continuous_transition"

        if run_count * self.cfg.pattern_disconnected_comb_runs_mul > active_count:
            return True, "disconnected_comb"

        if (
            run_count == 1
            and active_count >= self.cfg.pattern_continuous_active_min
            and span_count >= self.cfg.pattern_continuous_span_min
            and max_bin_count * self.cfg.pattern_continuous_peak_denom <= total_pixel_count
            and extrema_count <= self.cfg.pattern_continuous_extrema_max
        ):
            return True, "continuous_artificial"

        if run_count == 1 and active_count >= self.cfg.pattern_special_continuous_active_min and span_count >= self.cfg.pattern_special_continuous_span_min:
            smooth_wide_special = (
                extrema_count <= self.cfg.pattern_special_continuous_extrema_max
                and max_bin_count * self.cfg.pattern_special_continuous_peak_denom <= total_pixel_count
            )
            plateau_edge_special = (
                extrema_count <= self.cfg.pattern_special_plateau_extrema_max
                and plateau_pair_count >= self.cfg.pattern_special_plateau_pair_min
                and edge_pair_count <= self.cfg.pattern_special_edge_pair_max
            )
            if smooth_wide_special or plateau_edge_special:
                return True, "special_continuous_artificial"

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
        knots = _build_anchor_pwl_knots(anchor_low, anchor_high, self.cfg)
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
