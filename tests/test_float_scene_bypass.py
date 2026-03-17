import numpy as np
import pytest

from float_scene_test_utils import (
    build_binary_frame,
    build_constant_plane,
    build_object_plane,
    process_plane,
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
