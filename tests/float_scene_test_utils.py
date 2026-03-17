from __future__ import annotations

from typing import Iterable

import numpy as np

from ddic_ce_float.discrete_scene_gain import FloatDiscreteSceneGainConfig, FloatDiscreteSceneGainModel


def make_float_model(**cfg_overrides: float | int | bool) -> FloatDiscreteSceneGainModel:
    cfg = FloatDiscreteSceneGainConfig(**cfg_overrides)
    return FloatDiscreteSceneGainModel(cfg)


def build_constant_plane(value: int, shape: tuple[int, int] = (32, 32)) -> np.ndarray:
    return np.full(shape, value, dtype=np.uint8)


def build_binary_frame(
    low_value: int,
    high_value: int,
    high_count: int,
    *,
    total: int = 100,
    as_plane: bool = False,
) -> list[int] | np.ndarray:
    samples = [low_value] * (total - high_count) + [high_value] * high_count
    if as_plane:
        side = int(round(total**0.5))
        return np.asarray(samples, dtype=np.uint8).reshape(side, side)
    return samples


def build_object_plane(
    background_value: int,
    object_value: int,
    *,
    object_ratio: float,
    shape: tuple[int, int] = (100, 100),
) -> np.ndarray:
    plane = np.full(shape, background_value, dtype=np.uint8)
    total = plane.size
    count = max(1, int(round(total * object_ratio)))
    flat = plane.reshape(-1)
    flat[-count:] = object_value
    return flat.reshape(shape)


def build_bright_scene_plane(shape: tuple[int, int] = (64, 64)) -> np.ndarray:
    return build_object_plane(176, 224, object_ratio=0.25, shape=shape)


def build_skin_tone_rgb_patch(shape: tuple[int, int] = (32, 32)) -> np.ndarray:
    rgb = np.full((*shape, 3), [96, 96, 96], dtype=np.uint8)
    row_start = shape[0] // 4
    row_end = (3 * shape[0]) // 4
    col_start = shape[1] // 4
    col_end = (3 * shape[1]) // 4
    rgb[row_start:row_end, col_start:col_end] = [172, 132, 120]
    return rgb


def build_high_key_bucket() -> list[np.ndarray]:
    configs = (
        (172, 224, 0.25),
        (176, 224, 0.25),
        (180, 224, 0.30),
        (184, 232, 0.25),
    )
    return [build_object_plane(base, high, object_ratio=ratio, shape=(64, 64)) for base, high, ratio in configs]


def build_noise_bucket() -> list[np.ndarray]:
    rng = np.random.default_rng(7)
    planes: list[np.ndarray] = []
    for amplitude in (1, 2, 4, 8):
        noise = rng.integers(0, amplitude + 1, size=(128, 128), dtype=np.uint8)
        planes.append((12 + noise).astype(np.uint8))
    return planes


def make_slow_drift_sequence() -> list[np.ndarray]:
    base = np.tile(np.linspace(64, 192, 64, dtype=np.uint8), (64, 1))
    return [np.clip(base + offset, 0, 255).astype(np.uint8) for offset in range(5)]


def process_plane(
    plane: np.ndarray,
    **cfg_overrides: float | int | bool,
) -> tuple[object, np.ndarray]:
    model = make_float_model(scene_hold_enable=False, **cfg_overrides)
    result = model.process_frame(np.asarray(plane, dtype=np.uint8).reshape(-1).tolist())
    enhanced = np.asarray(result.mapped_samples, dtype=np.uint8).reshape(plane.shape)
    return result, enhanced


def classify_frame(
    frame: Iterable[int],
    **cfg_overrides: float | int | bool,
):
    model = make_float_model(scene_hold_enable=False, **cfg_overrides)
    return model.process_frame(list(frame))


def process_rgb(
    rgb: np.ndarray,
    **cfg_overrides: float | int | bool,
) -> tuple[object, np.ndarray]:
    model = make_float_model(scene_hold_enable=False, **cfg_overrides)
    result = model.process_rgb_frame(
        np.asarray(rgb, dtype=np.uint8).reshape(-1, 3).tolist(),
        cabc_enabled=False,
        aie_enabled=False,
    )
    enhanced = np.asarray(result.rgb_out, dtype=np.float32).reshape(rgb.shape)
    return result, enhanced


def max_plateau_length(row: np.ndarray) -> int:
    row_values = np.asarray(row).reshape(-1).tolist()
    if not row_values:
        return 0
    best = 1
    run = 1
    for left, right in zip(row_values, row_values[1:]):
        if left == right:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best


def gain_smoothness_metrics(gain_lut: Iterable[float]) -> tuple[float, float]:
    values = list(gain_lut)
    first = [values[index + 1] - values[index] for index in range(1, len(values) - 1)]
    second = [first[index + 1] - first[index] for index in range(len(first) - 1)]
    first_delta = max(abs(value) for value in first)
    second_delta = max(abs(value) for value in second)
    return float(first_delta), float(second_delta)


def count_scene_flips(scene_names: Iterable[str]) -> int:
    names = list(scene_names)
    return sum(left != right for left, right in zip(names, names[1:]))


def normalized_output_delta_ratio(inputs: list[np.ndarray], outputs: list[np.ndarray]) -> float:
    input_deltas = []
    output_deltas = []
    for prev_input, curr_input, prev_output, curr_output in zip(inputs, inputs[1:], outputs, outputs[1:]):
        input_delta = float(np.mean(np.abs(curr_input.astype(np.float32) - prev_input.astype(np.float32))))
        output_delta = float(np.mean(np.abs(curr_output.astype(np.float32) - prev_output.astype(np.float32))))
        input_deltas.append(input_delta)
        output_deltas.append(output_delta)

    mean_input_delta = float(np.mean(input_deltas))
    mean_output_delta = float(np.mean(output_deltas))
    return mean_output_delta / max(mean_input_delta, 1e-6)


def clip_ratio(array: np.ndarray) -> float:
    values = np.asarray(array, dtype=np.float32)
    return float(np.mean((values <= 0.0) | (values >= 255.0)))


def channel_ratio_relative_drift(before_rgb: np.ndarray, after_rgb: np.ndarray) -> float:
    before = np.asarray(before_rgb, dtype=np.float32)
    after = np.asarray(after_rgb, dtype=np.float32)
    valid = (
        (before[..., 0] < 250)
        & (before[..., 1] > 0)
        & (before[..., 1] < 250)
        & (before[..., 2] < 250)
        & (after[..., 0] < 250)
        & (after[..., 1] > 0)
        & (after[..., 1] < 250)
        & (after[..., 2] < 250)
    )
    if not np.any(valid):
        return 0.0
    before_ratio = before[..., 0][valid] / np.maximum(before[..., 1][valid], 1e-6)
    after_ratio = after[..., 0][valid] / np.maximum(after[..., 1][valid], 1e-6)
    relative = np.abs(after_ratio - before_ratio) / np.maximum(np.abs(before_ratio), 1e-6)
    return float(np.max(relative))
