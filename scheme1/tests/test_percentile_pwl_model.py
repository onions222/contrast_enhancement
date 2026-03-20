import numpy as np
import pytest
from pathlib import Path
from PIL import Image


def test_float_percentile_pwl_model_emits_monotonic_lut_and_tone_curve():
    from ce_scheme1.percentile_pwl import FloatPercentilePwlConfig, FloatPercentilePwlModel

    cfg = FloatPercentilePwlConfig(alpha_num=1, alpha_den=1)
    model = FloatPercentilePwlModel(cfg)

    result = model.process_frame([16, 24, 32, 48, 64, 96, 128, 192, 224])

    assert len(result.histogram) == cfg.n_bins
    assert len(result.lut) == cfg.lut_size
    assert len(result.tone_curve) == cfg.lut_size
    assert len(result.mapped_samples) == 9
    assert all(a <= b for a, b in zip(result.lut, result.lut[1:]))
    assert all(a <= b for a, b in zip(result.tone_curve, result.tone_curve[1:]))
    assert result.lut[0] == 0
    assert result.lut[-1] == cfg.input_max


def test_float_percentile_pwl_process_plane_image_matches_flattened_frame():
    from ce_scheme1.percentile_pwl import FloatPercentilePwlConfig, FloatPercentilePwlModel

    plane = np.array(
        [
            [12, 24, 36, 48],
            [60, 72, 84, 96],
            [108, 120, 132, 144],
            [156, 168, 180, 192],
        ],
        dtype=np.uint8,
    )
    cfg = FloatPercentilePwlConfig(alpha_num=1, alpha_den=1)

    frame_model = FloatPercentilePwlModel(cfg)
    plane_model = FloatPercentilePwlModel(cfg)
    frame_result = frame_model.process_frame(plane.reshape(-1).tolist())
    plane_result = plane_model.process_plane_image(plane)

    assert plane_result.histogram == frame_result.histogram
    assert plane_result.lut == frame_result.lut
    assert plane_result.mapped_samples == frame_result.mapped_samples


def test_float_percentile_pwl_empty_input_reuses_previous_lut_or_identity():
    from ce_scheme1.percentile_pwl import FloatPercentilePwlConfig, FloatPercentilePwlModel

    model = FloatPercentilePwlModel(FloatPercentilePwlConfig(alpha_num=1, alpha_den=4))

    first = model.process_frame([])
    assert first.lut == list(range(256))
    assert first.mapped_samples == []

    prior = model.process_frame([32, 64, 96, 128, 160, 192, 224])
    empty_after_valid = model.process_frame([])

    assert empty_after_valid.lut == prior.lut
    assert empty_after_valid.mapped_samples == []


def test_float_percentile_pwl_temporal_smoothing_reduces_lut_delta():
    from ce_scheme1.percentile_pwl import FloatPercentilePwlConfig, FloatPercentilePwlModel

    frame_a = [32] * 48 + [96] * 96 + [160] * 48
    frame_b = [36] * 48 + [100] * 96 + [164] * 48

    smooth_model = FloatPercentilePwlModel(
        FloatPercentilePwlConfig(alpha_num=1, alpha_den=4, enable_temporal_smoothing=True)
    )
    raw_model = FloatPercentilePwlModel(
        FloatPercentilePwlConfig(alpha_num=1, alpha_den=4, enable_temporal_smoothing=False)
    )

    smooth_model.process_frame(frame_a)
    raw_model.process_frame(frame_a)
    smooth_result = smooth_model.process_frame(frame_b)
    raw_result = raw_model.process_frame(frame_b)

    smooth_delta = sum(abs(a - b) for a, b in zip(smooth_model.prev_lut or [], smooth_result.lut))
    raw_delta = sum(abs(a - b) for a, b in zip(raw_model.prev_lut or [], raw_result.lut))

    assert smooth_delta <= raw_delta


def test_float_percentile_pwl_public_module_exports_expected_symbols():
    import ce_scheme1 as pkg

    assert hasattr(pkg, "FloatPercentilePwlConfig")
    assert hasattr(pkg, "FloatPercentilePwlFrameResult")
    assert hasattr(pkg, "FloatPercentilePwlModel")


def test_default_config_is_more_conservative_for_skin_closeup_image():
    from ce_scheme1.percentile_pwl import FloatPercentilePwlModel

    image_path = (
        Path("/Users/onion/Desktop/code/Contrast/data/raw/wikimedia_commons")
        / "faces_skin_closeup_blonde_girl.jpg"
    )
    rgb = np.asarray(Image.open(image_path).convert("RGB"), dtype=np.uint8)
    value_plane = rgb.max(axis=2)

    row_start = int(value_plane.shape[0] * 0.32)
    row_end = int(value_plane.shape[0] * 0.78)
    col_start = int(value_plane.shape[1] * 0.22)
    col_end = int(value_plane.shape[1] * 0.78)

    model = FloatPercentilePwlModel()
    result = model.process_plane_image(value_plane)
    mapped = np.asarray(result.mapped_samples, dtype=np.uint8).reshape(value_plane.shape)

    skin_crop = mapped[row_start:row_end, col_start:col_end]

    assert result.stats["gain"] <= 1.0
    assert float(skin_crop.std()) <= 46.0


def test_rgb_gain_blend_reduces_skin_closeup_texture_amplification():
    from ce_scheme1.percentile_pwl import (
        FloatPercentilePwlConfig,
        FloatPercentilePwlModel,
        apply_value_output_to_rgb_image,
    )

    image_path = (
        Path("/Users/onion/Desktop/code/Contrast/data/raw/wikimedia_commons")
        / "faces_skin_closeup_blonde_girl.jpg"
    )
    rgb = np.asarray(Image.open(image_path).convert("RGB"), dtype=np.uint8)
    value_plane = rgb.max(axis=2)

    row_start = int(value_plane.shape[0] * 0.32)
    row_end = int(value_plane.shape[0] * 0.78)
    col_start = int(value_plane.shape[1] * 0.22)
    col_end = int(value_plane.shape[1] * 0.78)

    cfg = FloatPercentilePwlConfig()
    model = FloatPercentilePwlModel(cfg)
    result = model.process_plane_image(value_plane)
    value_out = np.asarray(result.mapped_samples, dtype=np.uint8).reshape(value_plane.shape)

    full_gain_rgb = apply_value_output_to_rgb_image(rgb, value_out, rgb_gain_blend=1.0)
    blended_rgb = apply_value_output_to_rgb_image(rgb, value_out, rgb_gain_blend=cfg.rgb_gain_blend)

    full_skin_crop = full_gain_rgb[row_start:row_end, col_start:col_end].max(axis=2)
    blended_skin_crop = blended_rgb[row_start:row_end, col_start:col_end].max(axis=2)

    assert float(blended_skin_crop.std()) < float(full_skin_crop.std()) - 1.0
