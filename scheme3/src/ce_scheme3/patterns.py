from __future__ import annotations

import numpy as np


def generate_ramp_pattern(width: int, height: int, *, start: int = 0, stop: int = 255) -> np.ndarray:
    """生成水平灰阶 ramp 图，用于观察 LUT 的整体映射趋势。"""
    ramp = np.linspace(start, stop, num=width, dtype=np.float64)
    tiled = np.tile(ramp.astype(np.uint8), (height, 1))
    return tiled


def generate_bimodal_pattern(width: int, height: int, *, low: int = 32, high: int = 224) -> np.ndarray:
    """生成左右两半分别为低灰/高灰的双峰测试图。"""
    split = width // 2
    plane = np.full((height, width), high, dtype=np.uint8)
    plane[:, :split] = low
    return plane


def generate_noise_on_dark_pattern(
    width: int,
    height: int,
    *,
    base: int = 12,
    noise_amplitude: int = 8,
    seed: int = 13,
) -> np.ndarray:
    """生成暗背景上叠加随机噪声的测试图。"""
    rng = np.random.default_rng(seed)
    noise = rng.integers(0, noise_amplitude + 1, size=(height, width), dtype=np.uint8)
    plane = np.clip(base + noise.astype(np.uint16), 0, 255)
    return plane.astype(np.uint8)


def generate_skin_tone_patch_pattern(
    width: int,
    height: int,
    *,
    background: int = 96,
    patch: int = 172,
) -> np.ndarray:
    """生成带中央肤色亮度块的测试图，用于观察中灰和肤色保护。"""
    plane = np.full((height, width), background, dtype=np.uint8)
    row_start = height // 4
    row_end = max(row_start + 1, (3 * height) // 4)
    col_start = width // 4
    col_end = max(col_start + 1, (3 * width) // 4)
    plane[row_start:row_end, col_start:col_end] = patch
    return plane


def generate_pattern_suite(width: int = 256, height: int = 256) -> dict[str, dict[str, object]]:
    """生成一组常用算法验证 pattern 及对应元数据。"""
    patterns: dict[str, dict[str, object]] = {}
    ramps = {
        "ramp": generate_ramp_pattern(width, height, start=0, stop=255),
        "near_black_ramp": generate_ramp_pattern(width, height, start=0, stop=63),
        "near_white_ramp": generate_ramp_pattern(width, height, start=192, stop=255),
    }
    for name, plane in ramps.items():
        patterns[name] = {"plane": plane, "metadata": {"pattern": name}}

    patterns["flat_low_dynamic_range"] = {
        "plane": np.full((height, width), 96, dtype=np.uint8),
        "metadata": {"pattern": "flat_low_dynamic_range"},
    }
    patterns["bimodal"] = {
        "plane": generate_bimodal_pattern(width, height, low=24, high=200),
        "metadata": {"pattern": "bimodal"},
    }
    patterns["trimodal"] = {
        "plane": np.tile(
            np.concatenate(
                [
                    np.full(width // 3, 24, dtype=np.uint8),
                    np.full(width // 3, 128, dtype=np.uint8),
                    np.full(width - 2 * (width // 3), 220, dtype=np.uint8),
                ]
            ),
            (height, 1),
        ),
        "metadata": {"pattern": "trimodal"},
    }
    patterns["checkerboard"] = {
        "plane": ((np.indices((height, width)).sum(axis=0) % 2) * 255).astype(np.uint8),
        "metadata": {"pattern": "checkerboard"},
    }
    dark_object = np.full((height, width), 24, dtype=np.uint8)
    dark_object[height // 4 : (3 * height) // 4, width // 4 : (3 * width) // 4] = 220
    patterns["dark_background_bright_object"] = {
        "plane": dark_object,
        "metadata": {"pattern": "dark_background_bright_object"},
    }
    bright_object = np.full((height, width), 220, dtype=np.uint8)
    bright_object[height // 4 : (3 * height) // 4, width // 4 : (3 * width) // 4] = 24
    patterns["bright_background_dark_object"] = {
        "plane": bright_object,
        "metadata": {"pattern": "bright_background_dark_object"},
    }
    patterns["noise_on_dark"] = {
        "plane": generate_noise_on_dark_pattern(width, height, seed=13),
        "metadata": {"pattern": "noise_on_dark", "seed": 13},
    }
    patterns["skin_tone_patch"] = {
        "plane": generate_skin_tone_patch_pattern(width, height),
        "metadata": {"pattern": "skin_tone_patch"},
    }
    return patterns


# ---------------------------------------------------------------------------
# DDIC temporal transition sequence generators
# ---------------------------------------------------------------------------


def generate_scene_cut_sequence(
    width: int = 256,
    height: int = 256,
    *,
    from_value: int = 0,
    to_value: int = 192,
    frames: int = 5,
) -> list[np.ndarray]:
    """生成场景切换序列：前半帧为 from_value，后半帧为 to_value。"""
    seq: list[np.ndarray] = []
    mid = max(frames // 2, 1)
    for i in range(frames):
        value = from_value if i < mid else to_value
        seq.append(np.full((height, width), value, dtype=np.uint8))
    return seq


def generate_slow_fade_sequence(
    width: int = 256,
    height: int = 256,
    *,
    start_dr: int = 0,
    end_dr: int = 128,
    center: int = 128,
    frames: int = 8,
) -> list[np.ndarray]:
    """生成缓慢 DR 渐变序列：DR 从 start_dr 线性过渡到 end_dr。"""
    seq: list[np.ndarray] = []
    for i in range(frames):
        t = i / max(frames - 1, 1)
        dr = start_dr + (end_dr - start_dr) * t
        half_dr = dr / 2.0
        low = int(round(max(0, center - half_dr)))
        high = int(round(min(255, center + half_dr)))
        plane = np.full((height, width), low, dtype=np.uint8)
        plane[:, width // 2 :] = high
        seq.append(plane)
    return seq


def generate_bypass_boundary_oscillation_sequence(
    width: int = 256,
    height: int = 256,
    *,
    center: int = 128,
    dr_values: tuple[int, ...] = (3, 5, 3, 5, 3, 5, 3, 5),
) -> list[np.ndarray]:
    """生成 DR 在 bypass 阈值附近反复振荡的序列。"""
    seq: list[np.ndarray] = []
    for dr in dr_values:
        half_dr = dr // 2
        low = max(0, center - half_dr)
        high = min(255, center + half_dr + (dr % 2))
        plane = np.full((height, width), low, dtype=np.uint8)
        plane[:, width // 2 :] = high
        seq.append(plane)
    return seq

