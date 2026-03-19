from __future__ import annotations

import math
from typing import Iterable

import numpy as np


def summarize_plane(
    plane: np.ndarray,
    *,
    dark_threshold: int = 31,
    bright_threshold: int = 223,
    low_percentile: float = 2.0,
    high_percentile: float = 98.0,
) -> dict[str, float]:
    """汇总单个灰度平面的统计指标。

    输出覆盖基础亮度统计、动态范围、信息熵、百分位，以及暗区/亮区像素占比，
    适合用于算法前后效果对比或时域稳定性分析。
    """
    values = np.asarray(plane, dtype=np.uint8)
    flat = values.reshape(-1).astype(np.float64)
    hist = np.bincount(values.reshape(-1), minlength=256).astype(np.float64)
    probs = hist[hist > 0] / flat.size
    entropy = float(-np.sum(probs * np.log2(probs))) if probs.size else 0.0
    return {
        "mean": float(np.mean(flat)),
        "std": float(np.std(flat)),
        "min": float(np.min(flat)),
        "max": float(np.max(flat)),
        "dynamic_range": float(np.max(flat) - np.min(flat)),
        "entropy": entropy,
        "p2": float(np.percentile(flat, low_percentile)),
        "p98": float(np.percentile(flat, high_percentile)),
        "dark_ratio": float(np.mean(flat <= dark_threshold)),
        "bright_ratio": float(np.mean(flat >= bright_threshold)),
    }


def compute_ambe(before: np.ndarray, after: np.ndarray) -> float:
    """计算 AMBE，即增强前后平均亮度偏移的绝对值。"""
    before_values = np.asarray(before, dtype=np.float64)
    after_values = np.asarray(after, dtype=np.float64)
    return float(abs(np.mean(after_values) - np.mean(before_values)))


def compute_eme(plane: np.ndarray, *, block_size: int = 8, epsilon: float = 1.0) -> float:
    """计算 EME，对局部块对比度进行分块评估。

    图像会按 `block_size` 划分为小块，分别计算 `20*log10(max/min)` 形式的
    局部对比度分数，再取平均；`epsilon` 用于避免极小值导致的数值不稳定。
    """
    values = np.asarray(plane, dtype=np.uint8)
    height, width = values.shape
    scores: list[float] = []
    for row in range(0, height, block_size):
        for col in range(0, width, block_size):
            block = values[row : row + block_size, col : col + block_size]
            if block.size == 0:
                continue
            block_min = float(np.min(block))
            block_max = float(np.max(block))
            if math.isclose(block_max, block_min):
                scores.append(0.0)
                continue
            scores.append(20.0 * math.log10((block_max + epsilon) / (block_min + epsilon)))
    return float(np.mean(scores)) if scores else 0.0


def summarize_lut(lut: Iterable[int], *, prev_lut: Iterable[int] | None = None) -> dict[str, float]:
    """汇总 LUT 的单调性、覆盖范围及相邻帧变化量。"""
    lut_values = np.asarray(list(lut), dtype=np.float64)
    monotonic = float(np.all(np.diff(lut_values) >= 0))
    summary = {
        "monotonic": monotonic,
        "range_span": float(lut_values.max() - lut_values.min()),
        "full_range_coverage": float(lut_values[-1] - lut_values[0]),
    }
    if prev_lut is not None:
        prev_values = np.asarray(list(prev_lut), dtype=np.float64)
        delta = np.abs(lut_values - prev_values)
        summary["lut_mean_abs_delta"] = float(np.mean(delta))
        summary["lut_max_delta"] = float(np.max(delta))
    else:
        summary["lut_mean_abs_delta"] = 0.0
        summary["lut_max_delta"] = 0.0
    return summary


def summarize_temporal_change(
    prev_plane: np.ndarray,
    curr_plane: np.ndarray,
    prev_lut: Iterable[int],
    curr_lut: Iterable[int],
) -> dict[str, float]:
    """汇总相邻两帧图像和 LUT 的时域变化幅度。"""
    prev_values = np.asarray(prev_plane, dtype=np.float64)
    curr_values = np.asarray(curr_plane, dtype=np.float64)
    frame_delta = np.abs(curr_values - prev_values)
    lut_summary = summarize_lut(curr_lut, prev_lut=prev_lut)
    return {
        "frame_mean_abs_delta": float(np.mean(frame_delta)),
        "frame_max_abs_delta": float(np.max(frame_delta)),
        "lut_mean_abs_delta": lut_summary["lut_mean_abs_delta"],
        "lut_max_delta": lut_summary["lut_max_delta"],
    }
