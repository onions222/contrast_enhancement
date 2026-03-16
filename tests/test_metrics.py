import numpy as np


def test_summarize_plane_reports_expected_scalar_metrics():
    from ddic_ce.metrics import summarize_plane

    plane = np.array([[0, 0], [128, 255]], dtype=np.uint8)
    summary = summarize_plane(plane, dark_threshold=31, bright_threshold=223)

    assert summary["mean"] == 95.75
    assert summary["min"] == 0
    assert summary["max"] == 255
    assert summary["dynamic_range"] == 255.0
    assert summary["dark_ratio"] == 0.5
    assert summary["bright_ratio"] == 0.25
    assert 0.0 < summary["entropy"] < 3.0
    assert summary["p2"] == 0.0
    assert summary["p98"] > 240.0


def test_compute_ambe_returns_absolute_mean_difference():
    from ddic_ce.metrics import compute_ambe

    before = np.array([[10, 20], [30, 40]], dtype=np.uint8)
    after = np.array([[20, 30], [40, 50]], dtype=np.uint8)

    assert compute_ambe(before, after) == 10.0


def test_compute_eme_detects_higher_local_contrast():
    from ddic_ce.metrics import compute_eme

    flat = np.full((4, 4), 32, dtype=np.uint8)
    contrast = np.array(
        [
            [0, 255, 0, 255],
            [255, 0, 255, 0],
            [16, 240, 16, 240],
            [240, 16, 240, 16],
        ],
        dtype=np.uint8,
    )

    assert compute_eme(contrast, block_size=2) > compute_eme(flat, block_size=2)


def test_summarize_lut_reports_monotonicity_and_delta_metrics():
    from ddic_ce.metrics import summarize_lut

    prev_lut = [0, 1, 2, 3]
    curr_lut = [0, 2, 2, 5]
    summary = summarize_lut(curr_lut, prev_lut=prev_lut)

    assert summary["monotonic"] == 1.0
    assert summary["range_span"] == 5.0
    assert summary["full_range_coverage"] == 5.0
    assert summary["lut_mean_abs_delta"] == 0.75
    assert summary["lut_max_delta"] == 2.0


def test_summarize_temporal_change_tracks_frame_and_lut_deltas():
    from ddic_ce.metrics import summarize_temporal_change

    prev_plane = np.array([[10, 20], [30, 40]], dtype=np.uint8)
    curr_plane = np.array([[20, 20], [35, 45]], dtype=np.uint8)
    prev_lut = [0, 1, 2, 3]
    curr_lut = [0, 1, 3, 5]

    summary = summarize_temporal_change(prev_plane, curr_plane, prev_lut, curr_lut)

    assert summary["frame_mean_abs_delta"] == 5.0
    assert summary["frame_max_abs_delta"] == 10.0
    assert summary["lut_mean_abs_delta"] == 0.75
    assert summary["lut_max_delta"] == 2.0
