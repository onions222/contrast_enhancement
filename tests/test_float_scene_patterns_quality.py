import numpy as np

from ddic_ce.patterns import generate_noise_on_dark_pattern, generate_ramp_pattern
from ddic_ce.metrics import summarize_plane
from float_scene_test_utils import (
    build_high_key_bucket,
    max_plateau_length,
    process_plane,
)


def test_full_ramp_preserves_global_order_and_level_density():
    plane = generate_ramp_pattern(width=256, height=1, start=0, stop=255)
    _, enhanced = process_plane(plane)

    assert len(np.unique(enhanced[0])) >= 224
    assert max_plateau_length(enhanced[0]) <= 2


def test_near_black_ramp_preserves_minimum_shadow_level_count():
    plane = generate_ramp_pattern(width=64, height=1, start=0, stop=63)
    _, enhanced = process_plane(plane)

    assert len(np.unique(enhanced[0])) >= 48
    assert max_plateau_length(enhanced[0]) <= 2


def test_near_white_ramp_preserves_highlight_level_count():
    plane = generate_ramp_pattern(width=64, height=1, start=192, stop=255)
    _, enhanced = process_plane(plane)

    assert len(np.unique(enhanced[0])) >= 48
    assert max_plateau_length(enhanced[0]) <= 2


def test_high_key_bucket_limits_highlight_push():
    bright_ratio_deltas = []
    p99_values = []

    for plane in build_high_key_bucket():
        _, enhanced = process_plane(plane)
        before = summarize_plane(plane)
        after = summarize_plane(enhanced)
        bright_ratio_deltas.append(after["bright_ratio"] - before["bright_ratio"])
        p99_values.append(float(np.percentile(enhanced, 99)))

    assert float(np.median(bright_ratio_deltas)) <= 0.05
    assert sum(value < 255.0 for value in p99_values) >= int(0.9 * len(p99_values))


def test_dark_noise_bucket_does_not_expand_noise_std_more_than_guard_band():
    std_ratios = []
    for amplitude in (1, 2, 4, 8):
        plane = generate_noise_on_dark_pattern(width=128, height=128, base=12, noise_amplitude=amplitude, seed=7)
        _, enhanced = process_plane(plane)
        std_ratios.append(float(enhanced.std()) / max(float(plane.std()), 1e-6))

    assert max(std_ratios) <= 1.35
