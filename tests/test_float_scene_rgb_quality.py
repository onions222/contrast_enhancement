import numpy as np

from float_scene_test_utils import build_skin_tone_rgb_patch, channel_ratio_relative_drift, clip_ratio, process_rgb


def test_same_color_rgb_frame_bypasses_without_any_change():
    rgb = np.full((16, 16, 3), 96, dtype=np.uint8)
    result, enhanced = process_rgb(rgb)

    assert result.bypass_flag is True
    assert np.array_equal(enhanced, rgb.astype(np.float32))


def test_skin_tone_rgb_patch_keeps_channel_ratios_and_avoids_new_clipping():
    rgb = build_skin_tone_rgb_patch()
    _, enhanced = process_rgb(rgb)

    assert clip_ratio(enhanced) <= 0.02
    assert channel_ratio_relative_drift(rgb, enhanced) <= 0.03
