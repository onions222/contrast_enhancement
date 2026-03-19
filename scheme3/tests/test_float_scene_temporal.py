import numpy as np

from ce_scheme3.temporal_runner import run_temporal_sequence
from ce_scheme3.discrete_scene_gain_float import FloatDiscreteSceneGainConfig, FloatDiscreteSceneGainModel
from float_scene_test_utils import (
    build_bright_scene_plane,
    count_scene_flips,
    make_slow_drift_sequence,
    normalized_output_delta_ratio,
)


def test_hold_requires_second_confirmation_before_switching():
    cfg = FloatDiscreteSceneGainConfig()
    normal = np.tile(np.array([150] * 48 + [190] * 16, dtype=np.uint8), (64, 1))
    bright = build_bright_scene_plane()

    result = run_temporal_sequence([normal, bright, bright], cfg, model_cls=FloatDiscreteSceneGainModel)

    assert [frame["raw_scene_name"] for frame in result["frames"]] == ["Normal", "Bright", "Bright"]
    assert [frame["scene_name"] for frame in result["frames"]] == ["Normal", "Normal", "Bright"]


def test_scene_cut_switches_immediately_when_mean_delta_exceeds_cut_threshold():
    cfg = FloatDiscreteSceneGainConfig()
    low_mean = np.full((32, 32), 150, dtype=np.uint8)
    bright = build_bright_scene_plane(shape=(32, 32))

    result = run_temporal_sequence([low_mean, bright], cfg, model_cls=FloatDiscreteSceneGainModel)

    assert result["frames"][0]["scene_name"] == "Normal"
    assert result["frames"][1]["raw_scene_name"] == "Bright"
    assert result["frames"][1]["scene_name"] == "Bright"


def test_non_boundary_slow_drift_stays_scene_stable_without_lut_jitter():
    cfg = FloatDiscreteSceneGainConfig()
    frames = make_slow_drift_sequence()
    result = run_temporal_sequence(frames, cfg, model_cls=FloatDiscreteSceneGainModel)

    raw_scene_names = [frame["raw_scene_name"] for frame in result["frames"]]
    scene_names = [frame["scene_name"] for frame in result["frames"]]

    assert count_scene_flips(raw_scene_names) == 0
    assert count_scene_flips(scene_names) == 0
    assert max(frame["temporal"]["lut_mean_abs_delta"] for frame in result["frames"][1:]) == 0.0
    assert normalized_output_delta_ratio(frames, [frame["enhanced_plane"] for frame in result["frames"]]) <= 1.25


def test_low_light_noise_sequence_does_not_trigger_scene_jitter():
    cfg = FloatDiscreteSceneGainConfig()
    rng = np.random.default_rng(7)
    frames = [(12 + rng.integers(0, 5, size=(64, 64), dtype=np.uint8)).astype(np.uint8) for _ in range(8)]
    result = run_temporal_sequence(frames, cfg, model_cls=FloatDiscreteSceneGainModel)

    raw_scene_names = [frame["raw_scene_name"] for frame in result["frames"]]
    scene_names = [frame["scene_name"] for frame in result["frames"]]

    assert count_scene_flips(raw_scene_names) == 0
    assert count_scene_flips(scene_names) == 0
