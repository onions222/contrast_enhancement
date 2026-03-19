from ce_scheme3.metrics import summarize_plane
from float_scene_test_utils import build_high_key_bucket, build_noise_bucket, process_plane


def test_high_key_bucket_meets_bucket_level_highlight_limits():
    bright_ratio_deltas = []
    max_values = []

    for plane in build_high_key_bucket():
        _, enhanced = process_plane(plane)
        before = summarize_plane(plane)
        after = summarize_plane(enhanced)
        bright_ratio_deltas.append(after["bright_ratio"] - before["bright_ratio"])
        max_values.append(after["max"])

    assert sorted(bright_ratio_deltas)[len(bright_ratio_deltas) // 2] <= 0.05
    assert sum(value < 255.0 for value in max_values) >= int(0.9 * len(max_values))


def test_dark_noise_bucket_stays_within_noise_gain_guard_band():
    ratios = []
    for plane in build_noise_bucket():
        _, enhanced = process_plane(plane)
        ratios.append(float(enhanced.std()) / max(float(plane.std()), 1e-6))

    assert max(ratios) <= 1.35
