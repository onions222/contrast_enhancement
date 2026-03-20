import numpy as np
import pytest

from float_scene_test_utils import (
    build_binary_frame,
    build_banded_plane,
    build_comb_plane,
    build_color_bars_rgb,
    build_constant_plane,
    build_object_plane,
    build_single_channel_ramp_rgb,
    process_plane,
    process_rgb,
)


@pytest.mark.parametrize("value", [0, 16, 32, 64, 96, 128, 160, 192, 224, 240])
def test_same_color_frames_bypass_to_exact_identity(value: int):
    plane = build_constant_plane(value)
    result, enhanced = process_plane(plane)

    assert result.bypass_flag is True
    assert np.array_equal(enhanced, plane)
    assert result.tone_curve == pytest.approx([float(level) for level in range(256)])
    assert result.gain_lut[0] == pytest.approx(0.0)
    assert result.gain_lut[1:] == pytest.approx([1.0] * 255)


@pytest.mark.parametrize("span", [0, 1, 2, 3, 4])
def test_low_dynamic_range_frames_bypass_through_threshold(span: int):
    plane = build_object_plane(80, 80 + span, object_ratio=0.5, shape=(32, 32))
    result, enhanced = process_plane(plane)

    assert result.bypass_flag is True
    assert np.array_equal(enhanced, plane)


def test_low_dynamic_range_frames_stop_bypassing_above_threshold():
    plane = build_object_plane(79, 84, object_ratio=0.5, shape=(32, 32))
    result, enhanced = process_plane(plane)

    assert result.bypass_flag is False
    assert not np.array_equal(enhanced, plane)


def test_two_percent_bright_object_escapes_bypass():
    plane = build_object_plane(0, 224, object_ratio=0.02, shape=(10, 10))
    result, _ = process_plane(plane)

    assert result.bypass_flag is False
    assert result.scene_name == "Dark I"


def test_two_percent_dark_object_is_still_bypassed_today_and_stays_characterized():
    plane = build_object_plane(220, 24, object_ratio=0.02, shape=(10, 10))
    result, enhanced = process_plane(plane)

    assert result.bypass_flag is True
    assert np.array_equal(enhanced, plane)


def test_threshold_examples_stay_on_the_expected_side_of_bypass():
    assert process_plane(build_binary_frame(79, 83, 50, total=100, as_plane=True))[0].bypass_flag is True
    assert process_plane(build_binary_frame(79, 84, 50, total=100, as_plane=True))[0].bypass_flag is False


def test_gray_ramp_pattern_bypasses_to_identity():
    plane = np.tile(np.arange(256, dtype=np.uint8), (32, 1))
    result, enhanced = process_plane(plane)

    assert result.bypass_flag is True
    assert np.array_equal(enhanced, plane)


def test_banded_pattern_bypasses_to_identity():
    plane = build_banded_plane([16, 48, 96, 160, 224], orientation="vertical", shape=(32, 40))
    result, enhanced = process_plane(plane)

    assert result.bypass_flag is True
    assert np.array_equal(enhanced, plane)


def test_comb_pattern_bypasses_to_identity():
    plane = build_comb_plane(0, 200, orientation="vertical", shape=(32, 64))
    result, enhanced = process_plane(plane)

    assert result.bypass_flag is True
    assert np.array_equal(enhanced, plane)


def test_color_bars_pattern_stays_identity_on_rgb_path_under_v_domain():
    rgb = build_color_bars_rgb()
    result, enhanced = process_rgb(rgb)

    assert result.scene_name == "Bright"
    assert np.allclose(enhanced, rgb.astype(np.float32))


def test_single_channel_blue_ramp_pattern_bypasses_on_rgb_path():
    rgb = build_single_channel_ramp_rgb(channel="b", levels=32, orientation="horizontal")
    result, enhanced = process_rgb(rgb)

    assert result.bypass_flag is True
    assert np.allclose(enhanced, rgb.astype(np.float32))


def test_natural_like_gradient_with_texture_does_not_bypass():
    base = np.tile(np.linspace(96, 224, 64, dtype=np.uint8), (64, 1))
    textured = np.clip(base + ((np.indices((64, 64)).sum(axis=0) % 5) - 2), 0, 255).astype(np.uint8)
    result, enhanced = process_plane(textured)

    assert result.bypass_flag is False
    assert not np.array_equal(enhanced, textured)


def test_histogram_like_ramp_but_spatially_shuffled_does_not_bypass():
    row = np.arange(256, dtype=np.uint8)
    shuffled = np.tile(np.roll(row, 37), (32, 1))
    shuffled[1::2] = shuffled[1::2, ::-1]
    result, enhanced = process_plane(shuffled)

    assert result.bypass_flag is True
    assert np.array_equal(enhanced, shuffled)


def test_pattern_bypass_uses_histogram_only_targets_dense_sparse_and_comb_patterns():
    from float_scene_test_utils import make_float_model

    model = make_float_model(scene_hold_enable=False)
    ramp = np.tile(np.arange(256, dtype=np.uint8), (32, 1))
    shuffled = np.tile(np.roll(np.arange(256, dtype=np.uint8), 37), (32, 1))
    shuffled[1::2] = shuffled[1::2, ::-1]
    comb = build_comb_plane(0, 200, orientation="vertical", shape=(32, 64))
    textured = np.clip(
        np.tile(np.linspace(96, 224, 64, dtype=np.uint8), (64, 1)) + ((np.indices((64, 64)).sum(axis=0) % 5) - 2),
        0,
        255,
    ).astype(np.uint8)

    assert model._pattern_histogram_candidate(ramp) is True
    assert model._detect_pattern_bypass(ramp) is True

    assert model._pattern_histogram_candidate(shuffled) is True
    assert model._detect_pattern_bypass(shuffled) is True

    assert model._pattern_histogram_candidate(comb) is True
    assert model._detect_pattern_bypass(comb) is True

    assert model._pattern_histogram_candidate(textured) is False
    assert model._detect_pattern_bypass(textured) is False
