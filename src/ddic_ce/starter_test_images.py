from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ddic_ce.dataset_manifest_builder import ManifestEntry, export_manifest_csv, export_selected_subset
from ddic_ce.image_io import rgb_to_luma
from ddic_ce.metrics import summarize_plane


REPO_ROOT = Path(__file__).resolve().parents[2]
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
    plane = rgb_to_luma(rgb)
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
        mean_luma=float(summary["mean"]),
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
