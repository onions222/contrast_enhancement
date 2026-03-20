from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ce_scheme3.dataset_manifest_builder import ManifestEntry, export_manifest_csv, export_selected_subset
from ce_scheme3.image_io import rgb_to_value
from ce_scheme3.metrics import summarize_plane


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RAW_ROOT = REPO_ROOT / "data" / "raw" / "starter_synth_v1"
DEFAULT_MANIFEST_PATH = REPO_ROOT / "data" / "derived" / "manifests" / "2026-03-17-starter_synth_v1_manifest.csv"
DEFAULT_EVAL_SUBSET_ROOT = REPO_ROOT / "data" / "derived" / "eval_subsets"


@dataclass(frozen=True)
class StarterDatasetConfig:
    dataset_id: str = "starter_synth_v1"
    source: str = "Local Synthetic Starter Set"
    source_url: str = "local://starter_synth_v1"
    license_name: str = "generated-local"
    split: str = "test"
    width: int = 256
    height: int = 256
    raw_root: Path = DEFAULT_RAW_ROOT
    manifest_path: Path = DEFAULT_MANIFEST_PATH
    eval_subset_root: Path = DEFAULT_EVAL_SUBSET_ROOT


@dataclass(frozen=True)
class StarterImageSpec:
    filename: str
    scene_tag: str
    difficulty_tags: tuple[str, ...]
    expected_failure_modes: tuple[str, ...]
    notes: str
    builder_name: str


def _neutral_rgb_from_plane(plane: np.ndarray) -> np.ndarray:
    return np.repeat(plane[..., None], 3, axis=2).astype(np.uint8)


def _fill_rect(image: np.ndarray, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
    height, width = image.shape[:2]
    x0 = max(0, min(width, x0))
    x1 = max(0, min(width, x1))
    y0 = max(0, min(height, y0))
    y1 = max(0, min(height, y1))
    if x0 >= x1 or y0 >= y1:
        return
    image[y0:y1, x0:x1] = np.asarray(color, dtype=np.uint8)


def _horizontal_plane(width: int, height: int, start: int, stop: int) -> np.ndarray:
    line = np.linspace(start, stop, num=width, dtype=np.float64)
    return np.tile(np.clip(np.round(line), 0, 255).astype(np.uint8), (height, 1))


def _vertical_plane(width: int, height: int, start: int, stop: int) -> np.ndarray:
    column = np.linspace(start, stop, num=height, dtype=np.float64)[:, None]
    return np.tile(np.clip(np.round(column), 0, 255).astype(np.uint8), (1, width))


def _stepped_values(levels: int, size: int) -> np.ndarray:
    if size <= 0:
        return np.zeros((0,), dtype=np.uint8)
    if levels <= 1:
        return np.zeros((size,), dtype=np.uint8)
    stops = np.linspace(0.0, 255.0, num=levels, dtype=np.float64)
    indices = np.floor(np.linspace(0, levels, num=size, endpoint=False)).astype(int)
    indices = np.clip(indices, 0, levels - 1)
    return np.clip(np.round(stops[indices]), 0, 255).astype(np.uint8)


def _stepped_plane(width: int, height: int, levels: int, orientation: str) -> np.ndarray:
    if orientation == "horizontal":
        return np.tile(_stepped_values(levels, width), (height, 1))
    if orientation == "vertical":
        return np.tile(_stepped_values(levels, height)[:, None], (1, width))
    raise ValueError(f"Unsupported orientation: {orientation}")


def _add_noise(image: np.ndarray, amplitude: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noise = rng.integers(-amplitude, amplitude + 1, size=image.shape, endpoint=False)
    return np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def _checker_plane(width: int, height: int, low: int, high: int, block: int) -> np.ndarray:
    rows = np.arange(height) // max(block, 1)
    cols = np.arange(width) // max(block, 1)
    mask = (rows[:, None] + cols[None, :]) % 2
    return np.where(mask == 0, low, high).astype(np.uint8)


def _build_high_key_window(width: int, height: int) -> np.ndarray:
    plane = ((0.6 * _vertical_plane(width, height, 230, 246)) + (0.4 * _horizontal_plane(width, height, 220, 250))).astype(np.uint8)
    image = np.stack(
        [
            np.clip(plane + 6, 0, 255),
            np.clip(plane + 3, 0, 255),
            plane,
        ],
        axis=2,
    ).astype(np.uint8)
    _fill_rect(image, int(width * 0.62), int(height * 0.08), int(width * 0.94), int(height * 0.84), (250, 250, 248))
    _fill_rect(image, int(width * 0.56), int(height * 0.08), int(width * 0.62), int(height * 0.92), (190, 190, 186))
    _fill_rect(image, 0, int(height * 0.80), width, height, (212, 210, 206))
    return image


def _build_high_key_document(width: int, height: int) -> np.ndarray:
    image = np.full((height, width, 3), (242, 242, 240), dtype=np.uint8)
    _fill_rect(image, int(width * 0.08), int(height * 0.08), int(width * 0.92), int(height * 0.18), (224, 224, 222))
    _fill_rect(image, int(width * 0.08), int(height * 0.22), int(width * 0.45), int(height * 0.68), (234, 234, 232))
    _fill_rect(image, int(width * 0.52), int(height * 0.22), int(width * 0.92), int(height * 0.68), (236, 236, 234))
    for row in range(int(height * 0.24), int(height * 0.78), 14):
        _fill_rect(image, int(width * 0.12), row, int(width * 0.40), row + 3, (192, 192, 190))
    for row in range(int(height * 0.24), int(height * 0.78), 18):
        _fill_rect(image, int(width * 0.56), row, int(width * 0.88), row + 3, (198, 198, 196))
    return image


def _build_high_key_backlit_room(width: int, height: int) -> np.ndarray:
    plane = ((0.7 * _vertical_plane(width, height, 216, 248)) + (0.3 * _horizontal_plane(width, height, 228, 246))).astype(np.uint8)
    image = np.stack([plane + 4, plane + 2, plane], axis=2).clip(0, 255).astype(np.uint8)
    _fill_rect(image, 0, int(height * 0.70), width, height, (188, 184, 178))
    _fill_rect(image, int(width * 0.10), int(height * 0.54), int(width * 0.30), int(height * 0.88), (88, 82, 76))
    _fill_rect(image, int(width * 0.62), int(height * 0.48), int(width * 0.84), int(height * 0.90), (72, 70, 66))
    _fill_rect(image, int(width * 0.40), int(height * 0.12), int(width * 0.58), int(height * 0.48), (248, 248, 244))
    return image


def _build_normal_indoor_blocks(width: int, height: int) -> np.ndarray:
    plane = ((0.5 * _vertical_plane(width, height, 92, 156)) + (0.5 * _horizontal_plane(width, height, 84, 164))).astype(np.uint8)
    image = np.stack([plane + 6, plane + 2, plane], axis=2).clip(0, 255).astype(np.uint8)
    _fill_rect(image, int(width * 0.12), int(height * 0.18), int(width * 0.42), int(height * 0.72), (86, 84, 80))
    _fill_rect(image, int(width * 0.48), int(height * 0.24), int(width * 0.86), int(height * 0.66), (164, 158, 150))
    _fill_rect(image, int(width * 0.18), int(height * 0.76), int(width * 0.82), int(height * 0.90), (128, 112, 96))
    return image


def _build_normal_landscape(width: int, height: int) -> np.ndarray:
    sky = np.stack(
        [
            _vertical_plane(width, height, 148, 204),
            _vertical_plane(width, height, 170, 214),
            _vertical_plane(width, height, 196, 232),
        ],
        axis=2,
    )
    image = sky.astype(np.uint8)
    horizon = int(height * 0.62)
    image[horizon:] = np.stack(
        [
            _vertical_plane(width, height - horizon, 72, 118),
            _vertical_plane(width, height - horizon, 96, 136),
            _vertical_plane(width, height - horizon, 58, 92),
        ],
        axis=2,
    ).astype(np.uint8)
    _fill_rect(image, int(width * 0.08), int(height * 0.54), int(width * 0.24), int(height * 0.58), (228, 228, 226))
    _fill_rect(image, int(width * 0.64), int(height * 0.48), int(width * 0.84), int(height * 0.54), (238, 238, 236))
    return image


def _build_skin_patch(width: int, height: int) -> np.ndarray:
    image = np.full((height, width, 3), (116, 128, 142), dtype=np.uint8)
    _fill_rect(image, int(width * 0.20), int(height * 0.18), int(width * 0.78), int(height * 0.86), (186, 144, 126))
    _fill_rect(image, int(width * 0.28), int(height * 0.30), int(width * 0.70), int(height * 0.40), (170, 132, 116))
    _fill_rect(image, int(width * 0.28), int(height * 0.58), int(width * 0.72), int(height * 0.70), (196, 156, 138))
    _fill_rect(image, int(width * 0.18), int(height * 0.06), int(width * 0.82), int(height * 0.18), (78, 68, 62))
    return image


def _build_low_key_midgray_detail(width: int, height: int) -> np.ndarray:
    image = np.full((height, width, 3), (20, 20, 22), dtype=np.uint8)
    _fill_rect(image, int(width * 0.16), int(height * 0.18), int(width * 0.84), int(height * 0.82), (88, 90, 94))
    for row in range(int(height * 0.24), int(height * 0.76), 18):
        _fill_rect(image, int(width * 0.22), row, int(width * 0.78), row + 3, (128, 132, 136))
    return image


def _build_low_key_small_bright_sign(width: int, height: int, box_size: int) -> np.ndarray:
    image = np.full((height, width, 3), (14, 14, 16), dtype=np.uint8)
    x0 = (width - box_size) // 2
    y0 = (height - box_size) // 2
    _fill_rect(image, x0, y0, x0 + box_size, y0 + box_size, (236, 220, 124))
    _fill_rect(image, x0 - 8, y0 - 8, x0 + box_size + 8, y0, (46, 44, 40))
    _fill_rect(image, x0 - 8, y0 + box_size, x0 + box_size + 8, y0 + box_size + 8, (46, 44, 40))
    return image


def _build_low_key_noise_room(width: int, height: int) -> np.ndarray:
    image = np.full((height, width, 3), (10, 12, 16), dtype=np.uint8)
    image = _add_noise(image, amplitude=7, seed=17)
    _fill_rect(image, int(width * 0.20), int(height * 0.18), int(width * 0.72), int(height * 0.82), (28, 30, 34))
    _fill_rect(image, int(width * 0.62), int(height * 0.22), int(width * 0.78), int(height * 0.44), (102, 86, 64))
    return image


def _build_low_key_neon(width: int, height: int) -> np.ndarray:
    image = np.full((height, width, 3), (12, 10, 18), dtype=np.uint8)
    _fill_rect(image, int(width * 0.18), int(height * 0.22), int(width * 0.82), int(height * 0.78), (24, 20, 34))
    _fill_rect(image, int(width * 0.28), int(height * 0.40), int(width * 0.72), int(height * 0.58), (224, 78, 198))
    _fill_rect(image, int(width * 0.32), int(height * 0.44), int(width * 0.68), int(height * 0.54), (246, 210, 238))
    return image


def _build_low_key_shadow_texture(width: int, height: int) -> np.ndarray:
    plane = _checker_plane(width, height, 14, 28, 16)
    image = np.stack([plane, plane, plane + 2], axis=2).clip(0, 255).astype(np.uint8)
    _fill_rect(image, int(width * 0.10), int(height * 0.14), int(width * 0.88), int(height * 0.24), (38, 38, 42))
    return image


def _build_gradient_full(width: int, height: int) -> np.ndarray:
    plane = _horizontal_plane(width, height, 0, 255)
    return _neutral_rgb_from_plane(plane)


def _build_gradient_near_black(width: int, height: int) -> np.ndarray:
    plane = _horizontal_plane(width, height, 0, 63)
    return _neutral_rgb_from_plane(plane)


def _build_gradient_near_white(width: int, height: int) -> np.ndarray:
    plane = _horizontal_plane(width, height, 192, 255)
    return _neutral_rgb_from_plane(plane)


def _build_low_dr_flat(width: int, height: int) -> np.ndarray:
    return np.full((height, width, 3), (118, 118, 118), dtype=np.uint8)


def _build_low_dr_subtle_blocks(width: int, height: int) -> np.ndarray:
    image = np.full((height, width, 3), (120, 120, 120), dtype=np.uint8)
    _fill_rect(image, int(width * 0.16), int(height * 0.18), int(width * 0.46), int(height * 0.52), (122, 122, 122))
    _fill_rect(image, int(width * 0.54), int(height * 0.24), int(width * 0.84), int(height * 0.62), (118, 118, 118))
    return image


def _build_bimodal(width: int, height: int) -> np.ndarray:
    image = np.full((height, width, 3), (214, 220, 228), dtype=np.uint8)
    image[:, : width // 2] = np.asarray((28, 34, 42), dtype=np.uint8)
    return image


def _build_trimodal(width: int, height: int) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    third = width // 3
    image[:, :third] = np.asarray((22, 24, 28), dtype=np.uint8)
    image[:, third : 2 * third] = np.asarray((112, 118, 126), dtype=np.uint8)
    image[:, 2 * third :] = np.asarray((220, 224, 230), dtype=np.uint8)
    return image


def _build_bright_bg_dark_object(width: int, height: int) -> np.ndarray:
    image = np.full((height, width, 3), (228, 228, 226), dtype=np.uint8)
    _fill_rect(image, int(width * 0.44), int(height * 0.44), int(width * 0.56), int(height * 0.56), (22, 22, 24))
    return image


def _build_dark_bg_bright_object(width: int, height: int) -> np.ndarray:
    image = np.full((height, width, 3), (18, 18, 20), dtype=np.uint8)
    _fill_rect(image, int(width * 0.38), int(height * 0.38), int(width * 0.62), int(height * 0.62), (230, 230, 228))
    return image


def _build_text_ui_dark(width: int, height: int) -> np.ndarray:
    image = np.full((height, width, 3), (26, 28, 32), dtype=np.uint8)
    _fill_rect(image, 0, 0, width, int(height * 0.16), (44, 48, 54))
    for row in range(int(height * 0.24), int(height * 0.82), 18):
        _fill_rect(image, int(width * 0.10), row, int(width * 0.72), row + 4, (94, 102, 110))
    _fill_rect(image, int(width * 0.76), int(height * 0.26), int(width * 0.92), int(height * 0.76), (68, 84, 108))
    _fill_rect(image, int(width * 0.78), int(height * 0.30), int(width * 0.90), int(height * 0.38), (160, 182, 206))
    return image


def _build_text_ui_light(width: int, height: int) -> np.ndarray:
    image = np.full((height, width, 3), (238, 238, 236), dtype=np.uint8)
    _fill_rect(image, 0, 0, width, int(height * 0.16), (220, 220, 218))
    for row in range(int(height * 0.24), int(height * 0.80), 16):
        _fill_rect(image, int(width * 0.10), row, int(width * 0.72), row + 3, (160, 160, 158))
    _fill_rect(image, int(width * 0.76), int(height * 0.24), int(width * 0.92), int(height * 0.76), (190, 206, 228))
    _fill_rect(image, int(width * 0.78), int(height * 0.30), int(width * 0.90), int(height * 0.40), (96, 146, 204))
    return image


def _build_hard_shadow(width: int, height: int) -> np.ndarray:
    plane = _horizontal_plane(width, height, 20, 220)
    plane[:, : width // 2] = np.clip(plane[:, : width // 2] - 80, 0, 255)
    image = np.stack([plane + 2, plane, plane], axis=2).clip(0, 255).astype(np.uint8)
    _fill_rect(image, int(width * 0.46), 0, int(width * 0.54), height, (28, 28, 28))
    return image


def _build_color_bars(width: int, height: int) -> np.ndarray:
    colors = [
        (208, 48, 48),
        (224, 156, 52),
        (204, 200, 64),
        (72, 176, 74),
        (64, 168, 208),
        (80, 98, 210),
        (182, 74, 188),
    ]
    stripe_width = max(width // len(colors), 1)
    image = np.zeros((height, width, 3), dtype=np.uint8)
    for index, color in enumerate(colors):
        x0 = index * stripe_width
        x1 = width if index == len(colors) - 1 else min(width, (index + 1) * stripe_width)
        _fill_rect(image, x0, 0, x1, height, color)
    image = _add_noise(image, amplitude=2, seed=31)
    return image


def _build_channel_ramp(width: int, height: int, *, channel: str, levels: int, orientation: str) -> np.ndarray:
    plane = _stepped_plane(width, height, levels, orientation)
    image = np.zeros((height, width, 3), dtype=np.uint8)
    channel_map = {"r": 0, "g": 1, "b": 2}
    image[..., channel_map[channel]] = plane
    return image


def _build_gray_ramp(width: int, height: int, *, levels: int, orientation: str) -> np.ndarray:
    return _neutral_rgb_from_plane(_stepped_plane(width, height, levels, orientation))


def _build_segmented_bars(
    width: int,
    height: int,
    *,
    colors: list[tuple[int, int, int]],
    orientation: str,
) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    segment_count = max(len(colors), 1)
    if orientation == "horizontal":
        segment = max(width // segment_count, 1)
        for index, color in enumerate(colors):
            x0 = index * segment
            x1 = width if index == segment_count - 1 else min(width, (index + 1) * segment)
            _fill_rect(image, x0, 0, x1, height, color)
        return image
    if orientation == "vertical":
        segment = max(height // segment_count, 1)
        for index, color in enumerate(colors):
            y0 = index * segment
            y1 = height if index == segment_count - 1 else min(height, (index + 1) * segment)
            _fill_rect(image, 0, y0, width, y1, color)
        return image
    raise ValueError(f"Unsupported orientation: {orientation}")


def _build_named_color_bars(width: int, height: int, *, pattern_name: str, orientation: str) -> np.ndarray:
    patterns = {
        "rgb_primary": [(255, 0, 0), (0, 255, 0), (0, 0, 255)],
        "rgbcmykw": [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255), (0, 255, 255), (255, 0, 255), (255, 255, 0), (255, 255, 255)],
        "ebu_75": [(191, 191, 191), (191, 191, 0), (0, 191, 191), (0, 191, 0), (191, 0, 191), (191, 0, 0), (0, 0, 191), (0, 0, 0)],
        "gray_skin_mix": [(0, 0, 0), (64, 64, 64), (128, 128, 128), (192, 192, 192), (255, 255, 255), (224, 172, 105), (198, 134, 118), (141, 85, 72)],
    }
    return _build_segmented_bars(width, height, colors=patterns[pattern_name], orientation=orientation)


# ---------------------------------------------------------------------------
# DDIC safety test image builders
# ---------------------------------------------------------------------------


def _build_pure_black(width: int, height: int) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


def _build_pure_white(width: int, height: int) -> np.ndarray:
    return np.full((height, width, 3), 255, dtype=np.uint8)


def _build_pure_gray_128(width: int, height: int) -> np.ndarray:
    return np.full((height, width, 3), 128, dtype=np.uint8)


def _build_near_black_uniform(width: int, height: int) -> np.ndarray:
    return np.full((height, width, 3), 2, dtype=np.uint8)


def _build_near_white_uniform(width: int, height: int) -> np.ndarray:
    return np.full((height, width, 3), 253, dtype=np.uint8)


def _build_dc_offset_1(width: int, height: int) -> np.ndarray:
    image = np.full((height, width, 3), 127, dtype=np.uint8)
    image[: height // 2] = 128
    return image


def _build_flat_with_single_hot_pixel(width: int, height: int) -> np.ndarray:
    image = np.full((height, width, 3), 128, dtype=np.uint8)
    cy, cx = height // 2, width // 2
    image[cy, cx] = (255, 255, 255)
    return image


def _build_flat_with_single_dead_pixel(width: int, height: int) -> np.ndarray:
    image = np.full((height, width, 3), 128, dtype=np.uint8)
    cy, cx = height // 2, width // 2
    image[cy, cx] = (0, 0, 0)
    return image


def _build_flat_with_border_artifact(width: int, height: int) -> np.ndarray:
    image = np.full((height, width, 3), 128, dtype=np.uint8)
    image[0, :] = 0
    image[-1, :] = 0
    return image


def _build_near_flat_with_sparse_noise(width: int, height: int) -> np.ndarray:
    rng = np.random.default_rng(42)
    image = np.full((height, width, 3), 120, dtype=np.uint8)
    noise = rng.integers(-1, 2, size=(height, width, 3))
    image = np.clip(image.astype(np.int16) + noise, 119, 121).astype(np.uint8)
    count = max(1, int(round(height * width * 0.001)))
    indices = rng.choice(height * width, size=count, replace=False)
    flat = image.reshape(-1, 3)
    flat[indices] = (200, 200, 200)
    return image


def _build_smpte_bars(width: int, height: int) -> np.ndarray:
    colors_top = [
        (192, 192, 192),
        (192, 192, 0),
        (0, 192, 192),
        (0, 192, 0),
        (192, 0, 192),
        (192, 0, 0),
        (0, 0, 192),
    ]
    colors_mid = [
        (0, 0, 192),
        (19, 19, 19),
        (192, 0, 192),
        (19, 19, 19),
        (0, 192, 192),
        (19, 19, 19),
        (192, 192, 192),
    ]
    colors_bot = [
        (0, 29, 67),
        (255, 255, 255),
        (41, 0, 62),
        (0, 0, 0),
        (0, 0, 0),
        (0, 0, 0),
        (0, 0, 0),
    ]
    image = np.zeros((height, width, 3), dtype=np.uint8)
    h_top = int(height * 0.67)
    h_mid = int(height * 0.08)
    stripe = max(width // 7, 1)
    for i, color in enumerate(colors_top):
        x0 = i * stripe
        x1 = width if i == 6 else (i + 1) * stripe
        _fill_rect(image, x0, 0, x1, h_top, color)
    for i, color in enumerate(colors_mid):
        x0 = i * stripe
        x1 = width if i == 6 else (i + 1) * stripe
        _fill_rect(image, x0, h_top, x1, h_top + h_mid, color)
    bot_stripe = max(width // 7, 1)
    for i, color in enumerate(colors_bot):
        x0 = i * bot_stripe
        x1 = width if i == 6 else (i + 1) * bot_stripe
        _fill_rect(image, x0, h_top + h_mid, x1, height, color)
    return image


def _build_vertical_stripe_bw(width: int, height: int) -> np.ndarray:
    cols = np.arange(width) % 2
    plane = (cols * 255).astype(np.uint8)
    return _neutral_rgb_from_plane(np.tile(plane, (height, 1)))


def _build_horizontal_stripe_bw(width: int, height: int) -> np.ndarray:
    rows = np.arange(height) % 2
    plane = (rows[:, None] * 255).astype(np.uint8)
    return _neutral_rgb_from_plane(np.tile(plane, (1, width)))


def _build_dot_matrix(width: int, height: int) -> np.ndarray:
    row_idx = np.arange(height) % 4
    col_idx = np.arange(width) % 4
    mask = (row_idx[:, None] == 0) & (col_idx[None, :] == 0)
    plane = np.where(mask, 255, 0).astype(np.uint8)
    return _neutral_rgb_from_plane(plane)


def _build_cross_hatch(width: int, height: int) -> np.ndarray:
    row_idx = np.arange(height) % 8
    col_idx = np.arange(width) % 8
    mask = (row_idx[:, None] == 0) | (col_idx[None, :] == 0)
    plane = np.where(mask, 255, 0).astype(np.uint8)
    return _neutral_rgb_from_plane(plane)


def _build_window_pattern(width: int, height: int) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    margin = max(width, height) // 4
    _fill_rect(image, margin, margin, width - margin, height - margin, (255, 255, 255))
    return image


def _build_reverse_window(width: int, height: int) -> np.ndarray:
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    margin = max(width, height) // 4
    _fill_rect(image, margin, margin, width - margin, height - margin, (0, 0, 0))
    return image


def _build_gray_step_wedge(width: int, height: int, *, levels: int) -> np.ndarray:
    plane = _stepped_plane(width, height, levels, "horizontal")
    return _neutral_rgb_from_plane(plane)


def _build_single_primary_full(width: int, height: int, *, channel: str) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    ch_map = {"r": 0, "g": 1, "b": 2}
    image[..., ch_map[channel]] = 255
    return image


def _build_flicker_pair_a(width: int, height: int) -> np.ndarray:
    return np.full((height, width, 3), 128, dtype=np.uint8)


def _build_flicker_pair_b(width: int, height: int) -> np.ndarray:
    return np.full((height, width, 3), 130, dtype=np.uint8)


def _build_shallow_ramp_dark(width: int, height: int) -> np.ndarray:
    plane = _horizontal_plane(width, height, 0, 16)
    return _neutral_rgb_from_plane(plane)


def _build_shallow_ramp_bright(width: int, height: int) -> np.ndarray:
    plane = _horizontal_plane(width, height, 240, 255)
    return _neutral_rgb_from_plane(plane)


def _build_diagonal_ramp(width: int, height: int) -> np.ndarray:
    x = np.linspace(0.0, 1.0, num=width, dtype=np.float64)
    y = np.linspace(0.0, 1.0, num=height, dtype=np.float64)
    diag = (x[None, :] + y[:, None]) / 2.0
    plane = np.clip(np.round(diag * 255), 0, 255).astype(np.uint8)
    return _neutral_rgb_from_plane(plane)


def _build_circular_gradient(width: int, height: int) -> np.ndarray:
    cx, cy = width / 2.0, height / 2.0
    x = np.arange(width, dtype=np.float64) - cx
    y = np.arange(height, dtype=np.float64) - cy
    dist = np.sqrt(x[None, :] ** 2 + y[:, None] ** 2)
    max_dist = max(np.sqrt(cx ** 2 + cy ** 2), 1.0)
    plane = np.clip(np.round(dist / max_dist * 255), 0, 255).astype(np.uint8)
    return _neutral_rgb_from_plane(plane)


def _build_max_code_all_channels(width: int, height: int) -> np.ndarray:
    return np.full((height, width, 3), 255, dtype=np.uint8)


def _build_gain_stress_dark_cluster(width: int, height: int) -> np.ndarray:
    rng = np.random.default_rng(99)
    values = rng.integers(1, 4, size=(height, width), dtype=np.uint8)
    return _neutral_rgb_from_plane(values)


def _build_alternating_0_255(width: int, height: int) -> np.ndarray:
    row = np.arange(width) % 2
    col = np.arange(height) % 2
    mask = (row[None, :] + col[:, None]) % 2
    plane = (mask * 255).astype(np.uint8)
    return _neutral_rgb_from_plane(plane)


# ---------------------------------------------------------------------------
# DDIC spatial-pattern test image builders
# ---------------------------------------------------------------------------


def _build_multi_stripe_bw(width: int, height: int, *, stripe_width: int) -> np.ndarray:
    cols = (np.arange(width) // stripe_width) % 2
    plane = (cols * 255).astype(np.uint8)
    return _neutral_rgb_from_plane(np.tile(plane, (height, 1)))


def _build_concentric_boxes(width: int, height: int) -> np.ndarray:
    plane = np.zeros((height, width), dtype=np.uint8)
    rings = max(min(width, height) // 16, 2)
    for i in range(rings):
        margin_y = int(i * height / (2 * rings))
        margin_x = int(i * width / (2 * rings))
        value = int(i * 255 / max(rings - 1, 1))
        plane[margin_y : height - margin_y, margin_x : width - margin_x] = value
    return _neutral_rgb_from_plane(plane)


def _build_zone_plate(width: int, height: int) -> np.ndarray:
    x = np.linspace(-1.0, 1.0, num=width, dtype=np.float64)
    y = np.linspace(-1.0, 1.0, num=height, dtype=np.float64)
    r2 = x[None, :] ** 2 + y[:, None] ** 2
    plane = np.clip(np.round(127.5 + 127.5 * np.cos(40.0 * r2)), 0, 255).astype(np.uint8)
    return _neutral_rgb_from_plane(plane)


def _build_bayer_dither(width: int, height: int) -> np.ndarray:
    bayer_4x4 = np.array(
        [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]],
        dtype=np.uint8,
    )
    tile_h = (height + 3) // 4
    tile_w = (width + 3) // 4
    plane = np.tile(bayer_4x4, (tile_h, tile_w))[:height, :width] * 16
    plane = np.clip(plane, 0, 255).astype(np.uint8)
    return _neutral_rgb_from_plane(plane)


def _build_uniform_noise(width: int, height: int) -> np.ndarray:
    rng = np.random.default_rng(77)
    plane = rng.integers(0, 256, size=(height, width), dtype=np.uint8)
    return _neutral_rgb_from_plane(plane)


def _build_gradient_with_stripes(width: int, height: int) -> np.ndarray:
    base = np.tile(np.linspace(0, 255, width, dtype=np.uint8), (height, 1))
    stripes = ((np.arange(height) // 4) % 2 * 30)[:, None]
    plane = np.clip(base.astype(np.int16) + stripes, 0, 255).astype(np.uint8)
    return _neutral_rgb_from_plane(plane)


def _build_radial_spokes(width: int, height: int) -> np.ndarray:
    cx, cy = width / 2.0, height / 2.0
    x = np.arange(width, dtype=np.float64) - cx
    y = np.arange(height, dtype=np.float64) - cy
    angle = np.arctan2(y[:, None], x[None, :])
    spoke_count = 12
    plane = ((angle / (2.0 * np.pi / spoke_count)).astype(int) % 2 * 255).astype(np.uint8)
    return _neutral_rgb_from_plane(plane)


def _build_text_lines_dark(width: int, height: int) -> np.ndarray:
    plane = np.zeros((height, width), dtype=np.uint8)
    margin_x = max(width // 12, 2)
    line_height = 3
    spacing = max(height // 10, 6)
    y = spacing
    while y + line_height < height:
        plane[y : y + line_height, margin_x : width - margin_x] = 200
        y += spacing
    return _neutral_rgb_from_plane(plane)


IMAGE_BUILDERS = {
    "high_key_window": _build_high_key_window,
    "high_key_document": _build_high_key_document,
    "high_key_backlit_room": _build_high_key_backlit_room,
    "normal_indoor_blocks": _build_normal_indoor_blocks,
    "normal_landscape": _build_normal_landscape,
    "skin_patch": _build_skin_patch,
    "low_key_midgray_detail": _build_low_key_midgray_detail,
    "low_key_small_bright_sign_1pct": lambda width, height: _build_low_key_small_bright_sign(width, height, box_size=24),
    "low_key_small_bright_sign_2pct": lambda width, height: _build_low_key_small_bright_sign(width, height, box_size=36),
    "low_key_noise_room": _build_low_key_noise_room,
    "low_key_neon": _build_low_key_neon,
    "low_key_shadow_texture": _build_low_key_shadow_texture,
    "gradient_full": _build_gradient_full,
    "gradient_near_black": _build_gradient_near_black,
    "gradient_near_white": _build_gradient_near_white,
    "low_dr_flat": _build_low_dr_flat,
    "low_dr_subtle_blocks": _build_low_dr_subtle_blocks,
    "bimodal_split": _build_bimodal,
    "trimodal_bands": _build_trimodal,
    "bright_bg_dark_object": _build_bright_bg_dark_object,
    "dark_bg_bright_object": _build_dark_bg_bright_object,
    "text_ui_dark_menu": _build_text_ui_dark,
    "text_ui_light_page": _build_text_ui_light,
    "hard_shadow_scene": _build_hard_shadow,
    "color_bars_soft": _build_color_bars,
    # DDIC safety: pure color / extreme low DR boundary
    "pure_black": _build_pure_black,
    "pure_white": _build_pure_white,
    "pure_gray_128": _build_pure_gray_128,
    "near_black_uniform": _build_near_black_uniform,
    "near_white_uniform": _build_near_white_uniform,
    "dc_offset_1": _build_dc_offset_1,
    # DDIC safety: anomaly pixels
    "flat_hot_pixel": _build_flat_with_single_hot_pixel,
    "flat_dead_pixel": _build_flat_with_single_dead_pixel,
    "flat_border_artifact": _build_flat_with_border_artifact,
    "near_flat_sparse_noise": _build_near_flat_with_sparse_noise,
    # DDIC safety: factory patterns
    "smpte_bars": _build_smpte_bars,
    "vertical_stripe_bw": _build_vertical_stripe_bw,
    "horizontal_stripe_bw": _build_horizontal_stripe_bw,
    "dot_matrix": _build_dot_matrix,
    "cross_hatch": _build_cross_hatch,
    "window_pattern": _build_window_pattern,
    "reverse_window": _build_reverse_window,
    "gray_step_wedge_16": lambda w, h: _build_gray_step_wedge(w, h, levels=16),
    "gray_step_wedge_64": lambda w, h: _build_gray_step_wedge(w, h, levels=64),
    "single_primary_r": lambda w, h: _build_single_primary_full(w, h, channel="r"),
    "single_primary_g": lambda w, h: _build_single_primary_full(w, h, channel="g"),
    "single_primary_b": lambda w, h: _build_single_primary_full(w, h, channel="b"),
    "flicker_pair_a": _build_flicker_pair_a,
    "flicker_pair_b": _build_flicker_pair_b,
    # DDIC safety: banding sensitive
    "shallow_ramp_dark": _build_shallow_ramp_dark,
    "shallow_ramp_bright": _build_shallow_ramp_bright,
    "diagonal_ramp": _build_diagonal_ramp,
    "circular_gradient": _build_circular_gradient,
    # DDIC safety: overflow / boundary stress
    "max_code_all_channels": _build_max_code_all_channels,
    "gain_stress_dark_cluster": _build_gain_stress_dark_cluster,
    "alternating_0_255": _build_alternating_0_255,
    # DDIC spatial-pattern characterization
    "stripe_bw_3px": lambda w, h: _build_multi_stripe_bw(w, h, stripe_width=3),
    "stripe_bw_5px": lambda w, h: _build_multi_stripe_bw(w, h, stripe_width=5),
    "stripe_bw_8px": lambda w, h: _build_multi_stripe_bw(w, h, stripe_width=8),
    "concentric_boxes": _build_concentric_boxes,
    "zone_plate": _build_zone_plate,
    "bayer_dither": _build_bayer_dither,
    "uniform_noise": _build_uniform_noise,
    "gradient_with_stripes": _build_gradient_with_stripes,
    "radial_spokes": _build_radial_spokes,
    "text_lines_dark": _build_text_lines_dark,
}


STARTER_IMAGE_SPECS = [
    StarterImageSpec(
        filename="high_key_window_soft.png",
        scene_tag="high_key",
        difficulty_tags=("bright_dominant", "highlight_detail"),
        expected_failure_modes=("highlight_washout", "over_enhancement"),
        notes="High-key wall and window layout for highlight retention checks.",
        builder_name="high_key_window",
    ),
    StarterImageSpec(
        filename="high_key_document_page.png",
        scene_tag="high_key",
        difficulty_tags=("bright_dominant", "text_ui", "low_dynamic_range"),
        expected_failure_modes=("highlight_washout", "banding", "over_enhancement"),
        notes="Bright UI-like page with faint text blocks.",
        builder_name="high_key_document",
    ),
    StarterImageSpec(
        filename="high_key_backlit_room.png",
        scene_tag="high_key",
        difficulty_tags=("bright_dominant", "high_dynamic_range"),
        expected_failure_modes=("highlight_washout", "halo"),
        notes="Backlit indoor composition with dark silhouettes.",
        builder_name="high_key_backlit_room",
    ),
    StarterImageSpec(
        filename="normal_indoor_blocks.png",
        scene_tag="normal",
        difficulty_tags=("general",),
        expected_failure_modes=("general_quality_regression",),
        notes="Balanced indoor-style blocks for baseline scene behavior.",
        builder_name="normal_indoor_blocks",
    ),
    StarterImageSpec(
        filename="normal_landscape_like.png",
        scene_tag="normal",
        difficulty_tags=("general", "high_dynamic_range"),
        expected_failure_modes=("general_quality_regression", "halo"),
        notes="Sky-ground split with soft clouds and darker ground.",
        builder_name="normal_landscape",
    ),
    StarterImageSpec(
        filename="normal_skin_patch.png",
        scene_tag="normal",
        difficulty_tags=("skin_tone", "color_sensitive"),
        expected_failure_modes=("color_shift", "over_enhancement"),
        notes="Warm portrait-like patch for skin-tone and RGB drift checks.",
        builder_name="skin_patch",
    ),
    StarterImageSpec(
        filename="low_key_midgray_detail.png",
        scene_tag="low_key",
        difficulty_tags=("low_light", "dark_detail"),
        expected_failure_modes=("shadow_crush", "middle_gray_lift_error"),
        notes="Dark scene with meaningful mid-gray detail.",
        builder_name="low_key_midgray_detail",
    ),
    StarterImageSpec(
        filename="low_key_small_bright_sign_1pct.png",
        scene_tag="low_key",
        difficulty_tags=("low_light", "small_salient_object", "low_dynamic_range"),
        expected_failure_modes=("bypass_miss", "shadow_crush"),
        notes="Dark background with about 1 percent bright target.",
        builder_name="low_key_small_bright_sign_1pct",
    ),
    StarterImageSpec(
        filename="low_key_small_bright_sign_2pct.png",
        scene_tag="low_key",
        difficulty_tags=("low_light", "small_salient_object"),
        expected_failure_modes=("bypass_miss", "highlight_bloom"),
        notes="Dark background with about 2 percent bright target.",
        builder_name="low_key_small_bright_sign_2pct",
    ),
    StarterImageSpec(
        filename="low_key_noise_room.png",
        scene_tag="low_key",
        difficulty_tags=("low_light", "noisy_dark"),
        expected_failure_modes=("noise_boost", "shadow_crush"),
        notes="Low-light noisy room for dark-noise amplification checks.",
        builder_name="low_key_noise_room",
    ),
    StarterImageSpec(
        filename="low_key_neon_sign.png",
        scene_tag="low_key",
        difficulty_tags=("low_light", "high_dynamic_range", "color_sensitive"),
        expected_failure_modes=("noise_boost", "halo", "color_shift"),
        notes="Dark frame with bright neon-like sign.",
        builder_name="low_key_neon",
    ),
    StarterImageSpec(
        filename="low_key_shadow_texture.png",
        scene_tag="low_key",
        difficulty_tags=("low_light", "smooth_gradient"),
        expected_failure_modes=("banding", "shadow_crush"),
        notes="Low-key subtle checker texture for contour/banding checks.",
        builder_name="low_key_shadow_texture",
    ),
    StarterImageSpec(
        filename="gradient_full_ramp.png",
        scene_tag="normal",
        difficulty_tags=("smooth_gradient", "reference_ramp"),
        expected_failure_modes=("banding",),
        notes="Full-range ramp for LUT monotonicity and banding checks.",
        builder_name="gradient_full",
    ),
    StarterImageSpec(
        filename="gradient_near_black_ramp.png",
        scene_tag="low_key",
        difficulty_tags=("smooth_gradient", "reference_ramp", "low_light"),
        expected_failure_modes=("banding", "shadow_crush"),
        notes="Near-black ramp for dark detail retention checks.",
        builder_name="gradient_near_black",
    ),
    StarterImageSpec(
        filename="gradient_near_white_ramp.png",
        scene_tag="high_key",
        difficulty_tags=("smooth_gradient", "reference_ramp", "bright_dominant"),
        expected_failure_modes=("banding", "highlight_washout"),
        notes="Near-white ramp for highlight shaping checks.",
        builder_name="gradient_near_white",
    ),
    StarterImageSpec(
        filename="low_dr_flat_gray.png",
        scene_tag="normal",
        difficulty_tags=("low_dynamic_range",),
        expected_failure_modes=("bypass_miss",),
        notes="Flat low dynamic range frame that should normally bypass.",
        builder_name="low_dr_flat",
    ),
    StarterImageSpec(
        filename="low_dr_subtle_blocks.png",
        scene_tag="normal",
        difficulty_tags=("low_dynamic_range", "textured_low_dr"),
        expected_failure_modes=("bypass_miss", "over_enhancement"),
        notes="Subtle low-DR blocks near bypass boundary.",
        builder_name="low_dr_subtle_blocks",
    ),
    StarterImageSpec(
        filename="bimodal_split.png",
        scene_tag="normal",
        difficulty_tags=("bimodal_histogram",),
        expected_failure_modes=("scene_misclassification",),
        notes="Half dark and half bright split to stress summary-stat classification.",
        builder_name="bimodal_split",
    ),
    StarterImageSpec(
        filename="trimodal_bands.png",
        scene_tag="normal",
        difficulty_tags=("trimodal_histogram",),
        expected_failure_modes=("scene_misclassification",),
        notes="Three-band histogram stress case.",
        builder_name="trimodal_bands",
    ),
    StarterImageSpec(
        filename="bright_bg_dark_object.png",
        scene_tag="high_key",
        difficulty_tags=("small_salient_object", "bright_dominant"),
        expected_failure_modes=("scene_misclassification", "highlight_washout"),
        notes="Bright background with a small dark object.",
        builder_name="bright_bg_dark_object",
    ),
    StarterImageSpec(
        filename="dark_bg_bright_object.png",
        scene_tag="low_key",
        difficulty_tags=("small_salient_object", "low_light"),
        expected_failure_modes=("bypass_miss", "highlight_bloom"),
        notes="Dark background with a bright object larger than 2 percent.",
        builder_name="dark_bg_bright_object",
    ),
    StarterImageSpec(
        filename="text_ui_dark_menu.png",
        scene_tag="low_key",
        difficulty_tags=("text_ui", "low_light"),
        expected_failure_modes=("halo", "banding", "noise_boost"),
        notes="Dark menu-like layout with bright accents.",
        builder_name="text_ui_dark_menu",
    ),
    StarterImageSpec(
        filename="text_ui_light_page.png",
        scene_tag="high_key",
        difficulty_tags=("text_ui", "bright_dominant"),
        expected_failure_modes=("highlight_washout", "banding"),
        notes="Light document-like page for UI contrast checks.",
        builder_name="text_ui_light_page",
    ),
    StarterImageSpec(
        filename="hard_shadow_scene.png",
        scene_tag="normal",
        difficulty_tags=("high_dynamic_range", "edge_sensitive"),
        expected_failure_modes=("halo", "over_enhancement"),
        notes="Hard transition scene for halo and over-enhancement checks.",
        builder_name="hard_shadow_scene",
    ),
    StarterImageSpec(
        filename="color_bars_soft.png",
        scene_tag="normal",
        difficulty_tags=("color_sensitive", "saturated_colors"),
        expected_failure_modes=("color_shift", "saturation_clipping"),
        notes="Soft color bars for RGB path sanity checks.",
        builder_name="color_bars_soft",
    ),
    # --- DDIC safety: pure color / extreme low DR boundary ---
    StarterImageSpec(
        filename="ddic_pure_black.png",
        scene_tag="ddic_boundary",
        difficulty_tags=("pure_color", "zero_dr", "ddic_safety"),
        expected_failure_modes=("nonzero_output", "bypass_miss"),
        notes="All-zero frame for power-on / standby safety. Must bypass to exact identity.",
        builder_name="pure_black",
    ),
    StarterImageSpec(
        filename="ddic_pure_white.png",
        scene_tag="ddic_boundary",
        difficulty_tags=("pure_color", "zero_dr", "ddic_safety"),
        expected_failure_modes=("clipping", "bypass_miss"),
        notes="All-255 frame. Must bypass to exact identity.",
        builder_name="pure_white",
    ),
    StarterImageSpec(
        filename="ddic_pure_gray_128.png",
        scene_tag="ddic_boundary",
        difficulty_tags=("pure_color", "zero_dr", "ddic_safety"),
        expected_failure_modes=("bypass_miss",),
        notes="Uniform mid-gray with zero dynamic range.",
        builder_name="pure_gray_128",
    ),
    StarterImageSpec(
        filename="ddic_near_black_uniform.png",
        scene_tag="ddic_boundary",
        difficulty_tags=("pure_color", "zero_dr", "ddic_safety", "low_light"),
        expected_failure_modes=("noise_boost", "bypass_miss"),
        notes="Near-black R=G=B=2 frame. Must bypass without amplifying code values.",
        builder_name="near_black_uniform",
    ),
    StarterImageSpec(
        filename="ddic_near_white_uniform.png",
        scene_tag="ddic_boundary",
        difficulty_tags=("pure_color", "zero_dr", "ddic_safety", "bright_dominant"),
        expected_failure_modes=("clipping", "bypass_miss"),
        notes="Near-white R=G=B=253 frame. Must bypass without compressing code values.",
        builder_name="near_white_uniform",
    ),
    StarterImageSpec(
        filename="ddic_dc_offset_1.png",
        scene_tag="ddic_boundary",
        difficulty_tags=("minimal_dr", "ddic_safety"),
        expected_failure_modes=("bypass_miss", "over_enhancement"),
        notes="DR=1 frame (127 vs 128) at bypass threshold boundary.",
        builder_name="dc_offset_1",
    ),
    # --- DDIC safety: anomaly pixels on flat background ---
    StarterImageSpec(
        filename="ddic_flat_hot_pixel.png",
        scene_tag="ddic_boundary",
        difficulty_tags=("anomaly_pixel", "ddic_safety"),
        expected_failure_modes=("noise_boost", "over_enhancement"),
        notes="Flat 128 with single hot pixel at 255. Verifies single-outlier does not trigger enhancement.",
        builder_name="flat_hot_pixel",
    ),
    StarterImageSpec(
        filename="ddic_flat_dead_pixel.png",
        scene_tag="ddic_boundary",
        difficulty_tags=("anomaly_pixel", "ddic_safety"),
        expected_failure_modes=("noise_boost", "over_enhancement"),
        notes="Flat 128 with single dead pixel at 0.",
        builder_name="flat_dead_pixel",
    ),
    StarterImageSpec(
        filename="ddic_flat_border_artifact.png",
        scene_tag="ddic_boundary",
        difficulty_tags=("border_artifact", "ddic_safety"),
        expected_failure_modes=("noise_boost", "over_enhancement"),
        notes="Flat 128 with top and bottom rows at 0, simulating display black border.",
        builder_name="flat_border_artifact",
    ),
    StarterImageSpec(
        filename="ddic_near_flat_sparse_noise.png",
        scene_tag="ddic_boundary",
        difficulty_tags=("sparse_outlier", "ddic_safety"),
        expected_failure_modes=("noise_boost", "over_enhancement"),
        notes="Near-flat 120 ± 1 with 0.1% sparse bright outliers at 200.",
        builder_name="near_flat_sparse_noise",
    ),
    # --- DDIC safety: factory / OQC test patterns ---
    StarterImageSpec(
        filename="ddic_smpte_bars.png",
        scene_tag="ddic_factory",
        difficulty_tags=("factory_pattern", "ddic_safety", "color_bars"),
        expected_failure_modes=("pattern_enhancement", "color_shift"),
        notes="SMPTE color bars standard pattern. Must be bypassed to prevent factory test NG.",
        builder_name="smpte_bars",
    ),
    StarterImageSpec(
        filename="ddic_vertical_stripe_bw.png",
        scene_tag="ddic_factory",
        difficulty_tags=("factory_pattern", "ddic_safety", "stripe"),
        expected_failure_modes=("pattern_enhancement",),
        notes="1-pixel black/white vertical stripes for crosstalk / line defect test.",
        builder_name="vertical_stripe_bw",
    ),
    StarterImageSpec(
        filename="ddic_horizontal_stripe_bw.png",
        scene_tag="ddic_factory",
        difficulty_tags=("factory_pattern", "ddic_safety", "stripe"),
        expected_failure_modes=("pattern_enhancement",),
        notes="1-pixel black/white horizontal stripes.",
        builder_name="horizontal_stripe_bw",
    ),
    StarterImageSpec(
        filename="ddic_dot_matrix.png",
        scene_tag="ddic_factory",
        difficulty_tags=("factory_pattern", "ddic_safety", "periodic"),
        expected_failure_modes=("pattern_enhancement",),
        notes="Regular 4x4 dot matrix for pixel defect inspection.",
        builder_name="dot_matrix",
    ),
    StarterImageSpec(
        filename="ddic_cross_hatch.png",
        scene_tag="ddic_factory",
        difficulty_tags=("factory_pattern", "ddic_safety", "periodic"),
        expected_failure_modes=("pattern_enhancement",),
        notes="8-pixel period cross-hatch grid pattern.",
        builder_name="cross_hatch",
    ),
    StarterImageSpec(
        filename="ddic_window_pattern.png",
        scene_tag="ddic_factory",
        difficulty_tags=("factory_pattern", "ddic_safety", "window"),
        expected_failure_modes=("pattern_enhancement", "halo"),
        notes="White center window on black background, standard display uniformity test.",
        builder_name="window_pattern",
    ),
    StarterImageSpec(
        filename="ddic_reverse_window.png",
        scene_tag="ddic_factory",
        difficulty_tags=("factory_pattern", "ddic_safety", "window"),
        expected_failure_modes=("pattern_enhancement", "halo"),
        notes="Black center window on white background.",
        builder_name="reverse_window",
    ),
    StarterImageSpec(
        filename="ddic_gray_step_wedge_16.png",
        scene_tag="ddic_factory",
        difficulty_tags=("factory_pattern", "ddic_safety", "step_wedge"),
        expected_failure_modes=("banding", "pattern_enhancement"),
        notes="16-level gray step wedge for gamma verification.",
        builder_name="gray_step_wedge_16",
    ),
    StarterImageSpec(
        filename="ddic_gray_step_wedge_64.png",
        scene_tag="ddic_factory",
        difficulty_tags=("factory_pattern", "ddic_safety", "step_wedge"),
        expected_failure_modes=("banding", "pattern_enhancement"),
        notes="64-level gray step wedge for finer gamma verification.",
        builder_name="gray_step_wedge_64",
    ),
    StarterImageSpec(
        filename="ddic_single_primary_r.png",
        scene_tag="ddic_factory",
        difficulty_tags=("factory_pattern", "ddic_safety", "single_primary"),
        expected_failure_modes=("color_shift", "bypass_miss"),
        notes="Full-screen pure red R=255 for color filter test.",
        builder_name="single_primary_r",
    ),
    StarterImageSpec(
        filename="ddic_single_primary_g.png",
        scene_tag="ddic_factory",
        difficulty_tags=("factory_pattern", "ddic_safety", "single_primary"),
        expected_failure_modes=("color_shift", "bypass_miss"),
        notes="Full-screen pure green G=255 for color filter test.",
        builder_name="single_primary_g",
    ),
    StarterImageSpec(
        filename="ddic_single_primary_b.png",
        scene_tag="ddic_factory",
        difficulty_tags=("factory_pattern", "ddic_safety", "single_primary"),
        expected_failure_modes=("color_shift", "bypass_miss"),
        notes="Full-screen pure blue B=255 for color filter test.",
        builder_name="single_primary_b",
    ),
    StarterImageSpec(
        filename="ddic_flicker_pair_a.png",
        scene_tag="ddic_factory",
        difficulty_tags=("factory_pattern", "ddic_safety", "flicker"),
        expected_failure_modes=("flicker_amplification",),
        notes="Flicker test frame A (gray 128), paired with frame B.",
        builder_name="flicker_pair_a",
    ),
    StarterImageSpec(
        filename="ddic_flicker_pair_b.png",
        scene_tag="ddic_factory",
        difficulty_tags=("factory_pattern", "ddic_safety", "flicker"),
        expected_failure_modes=("flicker_amplification",),
        notes="Flicker test frame B (gray 130), paired with frame A. Delta must not be amplified.",
        builder_name="flicker_pair_b",
    ),
    # --- DDIC safety: banding sensitive regions ---
    StarterImageSpec(
        filename="ddic_shallow_ramp_dark.png",
        scene_tag="ddic_banding",
        difficulty_tags=("banding_sensitive", "ddic_safety", "low_light"),
        expected_failure_modes=("banding", "shadow_crush"),
        notes="Ultra-shallow ramp 0..16 in dark region where quantization banding is most visible on OLED.",
        builder_name="shallow_ramp_dark",
    ),
    StarterImageSpec(
        filename="ddic_shallow_ramp_bright.png",
        scene_tag="ddic_banding",
        difficulty_tags=("banding_sensitive", "ddic_safety", "bright_dominant"),
        expected_failure_modes=("banding", "highlight_washout"),
        notes="Ultra-shallow ramp 240..255 in highlight region.",
        builder_name="shallow_ramp_bright",
    ),
    StarterImageSpec(
        filename="ddic_diagonal_ramp.png",
        scene_tag="ddic_banding",
        difficulty_tags=("banding_sensitive", "ddic_safety", "smooth_gradient"),
        expected_failure_modes=("banding",),
        notes="45-degree diagonal gradient 0..255, sensitive to LUT staircasing.",
        builder_name="diagonal_ramp",
    ),
    StarterImageSpec(
        filename="ddic_circular_gradient.png",
        scene_tag="ddic_banding",
        difficulty_tags=("banding_sensitive", "ddic_safety", "smooth_gradient"),
        expected_failure_modes=("banding",),
        notes="Radial gradient from center, for 2D banding visibility check.",
        builder_name="circular_gradient",
    ),
    # --- DDIC safety: overflow / boundary stress ---
    StarterImageSpec(
        filename="ddic_max_code_all_channels.png",
        scene_tag="ddic_boundary",
        difficulty_tags=("overflow_stress", "ddic_safety"),
        expected_failure_modes=("overflow", "bypass_miss"),
        notes="All channels at max code 255. Verifies gain multiplication does not overflow.",
        builder_name="max_code_all_channels",
    ),
    StarterImageSpec(
        filename="ddic_gain_stress_dark_cluster.png",
        scene_tag="ddic_boundary",
        difficulty_tags=("overflow_stress", "ddic_safety", "low_light"),
        expected_failure_modes=("overflow", "gain_explosion"),
        notes="Random 1..3 code values. Stress test for gain_lut[1]=tone[1]/1 potential overflow.",
        builder_name="gain_stress_dark_cluster",
    ),
    StarterImageSpec(
        filename="ddic_alternating_0_255.png",
        scene_tag="ddic_boundary",
        difficulty_tags=("overflow_stress", "ddic_safety", "extreme_histogram"),
        expected_failure_modes=("overflow", "pattern_enhancement"),
        notes="Checkerboard 0/255 at pixel level. Maximum histogram bimodality stress.",
        builder_name="alternating_0_255",
    ),
    # --- DDIC spatial-pattern characterization ---
    # histogram_bypass_status documented in difficulty_tags for traceability:
    #   caught_by_sparse   = histogram has <=2 active bins, current sparse detector catches it
    #   caught_by_comb     = histogram has regular holes, current comb detector catches it
    #   evades_histogram   = dense histogram indistinguishable from natural scene, NOT caught
    StarterImageSpec(
        filename="ddic_stripe_bw_3px.png",
        scene_tag="ddic_spatial",
        difficulty_tags=("spatial_pattern", "ddic_safety", "stripe", "caught_by_sparse"),
        expected_failure_modes=("pattern_enhancement",),
        notes="3px wide B/W vertical stripes. Histogram: 2 active bins → caught by sparse detector.",
        builder_name="stripe_bw_3px",
    ),
    StarterImageSpec(
        filename="ddic_stripe_bw_5px.png",
        scene_tag="ddic_spatial",
        difficulty_tags=("spatial_pattern", "ddic_safety", "stripe", "caught_by_sparse"),
        expected_failure_modes=("pattern_enhancement",),
        notes="5px wide B/W vertical stripes. Histogram: 2 active bins → caught by sparse detector.",
        builder_name="stripe_bw_5px",
    ),
    StarterImageSpec(
        filename="ddic_stripe_bw_8px.png",
        scene_tag="ddic_spatial",
        difficulty_tags=("spatial_pattern", "ddic_safety", "stripe", "caught_by_sparse"),
        expected_failure_modes=("pattern_enhancement",),
        notes="8px wide B/W vertical stripes. Histogram: 2 active bins → caught by sparse detector.",
        builder_name="stripe_bw_8px",
    ),
    StarterImageSpec(
        filename="ddic_concentric_boxes.png",
        scene_tag="ddic_spatial",
        difficulty_tags=("spatial_pattern", "ddic_safety", "step_wedge", "caught_by_comb"),
        expected_failure_modes=("pattern_enhancement", "banding"),
        notes="Concentric rectangles at equal gray steps. Histogram: 16 active bins with 15 holes → caught by comb detector.",
        builder_name="concentric_boxes",
    ),
    StarterImageSpec(
        filename="ddic_zone_plate.png",
        scene_tag="ddic_spatial",
        difficulty_tags=("spatial_pattern", "ddic_safety", "frequency_sweep", "evades_histogram"),
        expected_failure_modes=("pattern_enhancement", "banding"),
        notes="Zone plate (concentric frequency sweep). Histogram: 32 active bins, DENSE, no holes → EVADES current bypass.",
        builder_name="zone_plate",
    ),
    StarterImageSpec(
        filename="ddic_bayer_dither.png",
        scene_tag="ddic_spatial",
        difficulty_tags=("spatial_pattern", "ddic_safety", "dither", "caught_by_comb"),
        expected_failure_modes=("pattern_enhancement",),
        notes="Bayer 4x4 ordered dither at 16 levels. Histogram: 16 active bins with 15 holes → caught by comb detector.",
        builder_name="bayer_dither",
    ),
    StarterImageSpec(
        filename="ddic_uniform_noise.png",
        scene_tag="ddic_spatial",
        difficulty_tags=("spatial_pattern", "ddic_safety", "noise", "evades_histogram"),
        expected_failure_modes=("pattern_enhancement", "noise_boost"),
        notes="Uniform random noise 0..255. Histogram: 32 active bins, flat distribution → EVADES current bypass. Looks like natural image to histogram.",
        builder_name="uniform_noise",
    ),
    StarterImageSpec(
        filename="ddic_gradient_with_stripes.png",
        scene_tag="ddic_spatial",
        difficulty_tags=("spatial_pattern", "ddic_safety", "composite", "evades_histogram"),
        expected_failure_modes=("pattern_enhancement", "banding"),
        notes="Horizontal gradient with overlaid horizontal stripes. Histogram: 32 active dense bins → EVADES current bypass.",
        builder_name="gradient_with_stripes",
    ),
    StarterImageSpec(
        filename="ddic_radial_spokes.png",
        scene_tag="ddic_spatial",
        difficulty_tags=("spatial_pattern", "ddic_safety", "radial", "caught_by_sparse"),
        expected_failure_modes=("pattern_enhancement",),
        notes="12-spoke radial B/W pattern. Histogram: 2 active bins → caught by sparse detector.",
        builder_name="radial_spokes",
    ),
    StarterImageSpec(
        filename="ddic_text_lines_dark.png",
        scene_tag="ddic_spatial",
        difficulty_tags=("spatial_pattern", "ddic_safety", "text_sim", "caught_by_sparse"),
        expected_failure_modes=("pattern_enhancement", "noise_boost"),
        notes="Dark background with repeating white text-like lines. Histogram: 2 active bins → caught by sparse detector.",
        builder_name="text_lines_dark",
    ),
]

for channel in ("r", "g", "b"):
    for levels in (256, 64, 32, 8):
        for orientation in ("horizontal", "vertical"):
            STARTER_IMAGE_SPECS.append(
                StarterImageSpec(
                    filename=f"rgb_ramp_{channel}_{levels}_{orientation}.png",
                    scene_tag="gradient",
                    difficulty_tags=("channel_ramp", f"levels_{levels}", orientation, channel),
                    expected_failure_modes=("banding", "color_shift"),
                    notes=f"Single-channel {channel.upper()} stepped ramp with {levels} levels in {orientation} direction.",
                    builder_name=f"rgb_ramp_{channel}_{levels}_{orientation}",
                )
            )

for levels in (256, 64, 32, 8):
    for orientation in ("horizontal", "vertical"):
        STARTER_IMAGE_SPECS.append(
            StarterImageSpec(
                filename=f"gray_ramp_{levels}_{orientation}.png",
                scene_tag="gradient",
                difficulty_tags=("gray_ramp", f"levels_{levels}", orientation),
                expected_failure_modes=("banding",),
                notes=f"Neutral grayscale stepped ramp with {levels} levels in {orientation} direction.",
                builder_name=f"gray_ramp_{levels}_{orientation}",
            )
        )

for pattern_name in ("rgb_primary", "rgbcmykw", "ebu_75", "gray_skin_mix"):
    for orientation in ("horizontal", "vertical"):
        STARTER_IMAGE_SPECS.append(
            StarterImageSpec(
                filename=f"color_bars_{pattern_name}_{orientation}.png",
                scene_tag="normal",
                difficulty_tags=("color_bars", pattern_name, orientation),
                expected_failure_modes=("color_shift", "clip_ratio", "banding"),
                notes=f"{pattern_name} color bars in {orientation} direction for RGB-path and clipping checks.",
                builder_name=f"color_bars_{pattern_name}_{orientation}",
            )
        )


def _render_image(spec: StarterImageSpec, width: int, height: int) -> np.ndarray:
    if spec.builder_name in IMAGE_BUILDERS:
        return IMAGE_BUILDERS[spec.builder_name](width, height)
    if spec.builder_name.startswith("rgb_ramp_"):
        _, _, channel, levels, orientation = spec.builder_name.split("_")
        return _build_channel_ramp(width, height, channel=channel, levels=int(levels), orientation=orientation)
    if spec.builder_name.startswith("gray_ramp_"):
        _, _, levels, orientation = spec.builder_name.split("_")
        return _build_gray_ramp(width, height, levels=int(levels), orientation=orientation)
    if spec.builder_name.startswith("color_bars_"):
        parts = spec.builder_name.split("_")
        orientation = parts[-1]
        pattern_name = "_".join(parts[2:-1])
        return _build_named_color_bars(width, height, pattern_name=pattern_name, orientation=orientation)
    raise KeyError(f"Unknown starter image builder: {spec.builder_name}")


def _build_manifest_entry(config: StarterDatasetConfig, spec: StarterImageSpec, rgb: np.ndarray) -> ManifestEntry:
    plane = rgb_to_value(rgb)
    summary = summarize_plane(plane)
    return ManifestEntry(
        dataset_id=config.dataset_id,
        source=config.source,
        source_url=config.source_url,
        license=config.license_name,
        local_root=str(config.raw_root),
        split=config.split,
        selected_count=1,
        scene_tag=spec.scene_tag,
        difficulty_tag="|".join(spec.difficulty_tags),
        expected_failure_modes="|".join(spec.expected_failure_modes),
        notes=spec.notes,
        filename=spec.filename,
        relative_path=spec.filename,
        width=int(rgb.shape[1]),
        height=int(rgb.shape[0]),
        mean_value=float(summary["mean"]),
        dark_ratio=float(summary["dark_ratio"]),
        bright_ratio=float(summary["bright_ratio"]),
        dynamic_range=float(summary["dynamic_range"]),
    )


def build_starter_test_images(config: StarterDatasetConfig | None = None) -> dict[str, object]:
    cfg = config or StarterDatasetConfig()
    cfg.raw_root.mkdir(parents=True, exist_ok=True)
    entries: list[ManifestEntry] = []
    written_files: list[Path] = []

    for spec in STARTER_IMAGE_SPECS:
        rgb = _render_image(spec, cfg.width, cfg.height)
        output_path = cfg.raw_root / spec.filename
        Image.fromarray(rgb).save(output_path)
        entries.append(_build_manifest_entry(cfg, spec, rgb))
        written_files.append(output_path)

    export_manifest_csv(cfg.manifest_path, entries)
    copied_files = export_selected_subset(entries, cfg.eval_subset_root)
    summary = {
        "dataset_id": cfg.dataset_id,
        "raw_root": str(cfg.raw_root),
        "manifest_path": str(cfg.manifest_path),
        "eval_subset_root": str(cfg.eval_subset_root),
        "image_count": len(entries),
        "scene_counts": {
            scene_tag: sum(1 for entry in entries if entry.scene_tag == scene_tag)
            for scene_tag in sorted({entry.scene_tag for entry in entries})
        },
        "written_files": [str(path) for path in written_files],
        "copied_files": [str(path) for path in copied_files],
    }
    return summary


def main() -> dict[str, object]:
    summary = build_starter_test_images()
    print(f"Starter test dataset ready: {summary['image_count']} images.")
    print(f"Manifest written to: {summary['manifest_path']}")
    print(f"Eval subset root: {summary['eval_subset_root']}")
    return summary


if __name__ == "__main__":
    main()
