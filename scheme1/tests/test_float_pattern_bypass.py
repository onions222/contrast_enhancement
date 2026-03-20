import numpy as np
from pathlib import Path
from PIL import Image

from ce_scheme1.percentile_pwl import FloatPercentilePwlConfig, FloatPercentilePwlModel
from ce_scheme1.image_io import rgb_to_value


STARTER_SYNTH_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "starter_synth_v1"


def _load_value_samples(image_name: str) -> list[int]:
    rgb = np.asarray(Image.open(STARTER_SYNTH_ROOT / image_name).convert("RGB"), dtype=np.uint8)
    return rgb_to_value(rgb).reshape(-1).tolist()


def test_topology_features_for_two_isolated_bins():
    model = FloatPercentilePwlModel()
    hist = [10, 0, 10] + [0] * 29

    features = model._topology_features_from_hist(hist, total_pixels=20)

    assert features["active_count"] == 2
    assert features["connectivity_count"] == 0
    assert features["run_count"] == 2
    assert features["span_count"] == 3
    assert features["max_bin_count"] == 10


def test_topology_features_for_single_continuous_run():
    model = FloatPercentilePwlModel()
    hist = [0] * 8 + [7, 8, 9, 8, 7] + [0] * 19

    features = model._topology_features_from_hist(hist, total_pixels=39)

    assert features["active_count"] == 5
    assert features["connectivity_count"] == 4
    assert features["run_count"] == 1
    assert features["span_count"] == 5
    assert features["first_active_bin"] == 8
    assert features["last_active_bin"] == 12


def test_pattern_bypass_detects_uniform_sparse():
    model = FloatPercentilePwlModel(FloatPercentilePwlConfig(pattern_bypass_enable=True))
    plane = np.full((32, 256), 96, dtype=np.uint8).reshape(-1).tolist()

    result = model.process_frame(plane)

    assert result.stats["pattern_bypass"] is True
    assert result.stats["pattern_bypass_reason"] == "uniform_sparse"
    assert np.allclose(result.tone_curve, np.arange(256))


def test_pattern_bypass_detects_disconnected_comb():
    model = FloatPercentilePwlModel(FloatPercentilePwlConfig(pattern_bypass_enable=True))
    bins = np.arange(0, 256, 16, dtype=np.uint8)
    plane = np.tile(bins, (64, 1)).reshape(-1).tolist()

    result = model.process_frame(plane)

    assert result.stats["pattern_bypass"] is True
    assert result.stats["pattern_bypass_reason"] == "disconnected_comb"
    assert np.allclose(result.tone_curve, np.arange(256))


def test_pattern_bypass_detects_continuous_artificial():
    model = FloatPercentilePwlModel(
        FloatPercentilePwlConfig(pattern_bypass_enable=True, enable_temporal_smoothing=False)
    )
    ramp = np.tile(np.arange(256, dtype=np.uint8), (32, 1)).reshape(-1).tolist()

    result = model.process_frame(ramp)

    assert result.stats["pattern_bypass"] is True
    assert result.stats["pattern_bypass_reason"] == "continuous_artificial"
    assert np.allclose(result.tone_curve, np.arange(256))


def test_pattern_bypass_detects_special_continuous_artificial_for_circular_gradient():
    model = FloatPercentilePwlModel(
        FloatPercentilePwlConfig(pattern_bypass_enable=True, enable_temporal_smoothing=False)
    )

    result = model.process_frame(_load_value_samples("ddic_circular_gradient.png"))

    assert result.stats["pattern_bypass"] is True
    assert result.stats["pattern_bypass_reason"] == "special_continuous_artificial"
    assert np.allclose(result.tone_curve, np.arange(256))


def test_pattern_bypass_detects_special_continuous_artificial_for_gradient_with_stripes():
    model = FloatPercentilePwlModel(
        FloatPercentilePwlConfig(pattern_bypass_enable=True, enable_temporal_smoothing=False)
    )

    result = model.process_frame(_load_value_samples("ddic_gradient_with_stripes.png"))

    assert result.stats["pattern_bypass"] is True
    assert result.stats["pattern_bypass_reason"] == "special_continuous_artificial"
    assert np.allclose(result.tone_curve, np.arange(256))


def test_pattern_bypass_keeps_reason_for_gradient_full_ramp():
    model = FloatPercentilePwlModel(
        FloatPercentilePwlConfig(pattern_bypass_enable=True, enable_temporal_smoothing=False)
    )

    result = model.process_frame(_load_value_samples("gradient_full_ramp.png"))

    assert result.stats["pattern_bypass"] is True
    assert result.stats["pattern_bypass_reason"] == "continuous_artificial"


def test_pattern_bypass_keeps_reason_for_near_black_ramp():
    model = FloatPercentilePwlModel(
        FloatPercentilePwlConfig(pattern_bypass_enable=True, enable_temporal_smoothing=False)
    )

    result = model.process_frame(_load_value_samples("gradient_near_black_ramp.png"))

    assert result.stats["pattern_bypass"] is True
    assert result.stats["pattern_bypass_reason"] == "narrow_continuous_transition"


def test_pattern_bypass_keeps_reason_for_step_wedge_16():
    model = FloatPercentilePwlModel(
        FloatPercentilePwlConfig(pattern_bypass_enable=True, enable_temporal_smoothing=False)
    )

    result = model.process_frame(_load_value_samples("ddic_gray_step_wedge_16.png"))

    assert result.stats["pattern_bypass"] is True
    assert result.stats["pattern_bypass_reason"] == "disconnected_comb"


def test_pattern_bypass_ignores_natural_like_image():
    model = FloatPercentilePwlModel(FloatPercentilePwlConfig(enable_temporal_smoothing=False))
    base = np.linspace(96, 224, 256, dtype=np.uint8)
    rng = np.random.default_rng(42)
    noise = rng.integers(-5, 6, size=256, endpoint=True)
    textured = np.clip(base + noise, 0, 255).astype(np.uint8)
    plane = np.tile(textured, (32, 1)).reshape(-1).tolist()

    result = model.process_frame(plane)

    assert result.stats["pattern_bypass"] is False
    assert result.stats["pattern_bypass_reason"] == ""
    assert not np.allclose(result.tone_curve, np.arange(256))


def test_pattern_bypass_can_be_disabled():
    model = FloatPercentilePwlModel(FloatPercentilePwlConfig(pattern_bypass_enable=False, enable_temporal_smoothing=False))
    ramp = np.tile(np.arange(256, dtype=np.uint8), (32, 1)).reshape(-1).tolist()

    result = model.process_frame(ramp)

    assert result.stats["pattern_bypass"] is False
    assert result.stats["pattern_bypass_reason"] == ""
    assert not np.allclose(result.tone_curve, np.arange(256))
