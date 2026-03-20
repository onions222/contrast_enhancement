import numpy as np

from ce_scheme3.image_io import rgb_to_value


def test_rgb_to_value_returns_uint8_plane_with_same_height_width():
    rgb = np.array([[[0, 0, 0], [255, 255, 255]]], dtype=np.uint8)
    value = rgb_to_value(rgb)
    assert value.shape == (1, 2)
    assert value.dtype == np.uint8
    assert int(value[0, 0]) == 0
    assert int(value[0, 1]) == 255


def test_rgb_to_value_uses_hsv_v_not_y_luma():
    rgb = np.array([[[255, 0, 0], [0, 200, 50], [10, 20, 30]]], dtype=np.uint8)

    value = rgb_to_value(rgb)

    assert value.tolist() == [[255, 200, 30]]


def test_apply_value_lut_to_rgb_preserves_shape_and_uint8_range():
    from ce_scheme3.image_io import apply_value_lut_to_rgb

    rgb = np.array([[[10, 20, 30], [100, 120, 140]]], dtype=np.uint8)
    lut = list(range(256))
    out = apply_value_lut_to_rgb(rgb, lut)
    assert out.shape == rgb.shape
    assert out.dtype == np.uint8
    assert int(out.min()) >= 0
    assert int(out.max()) <= 255


def test_process_rgb_image_returns_enhanced_rgb_lut_and_stats():
    from ce_scheme3.image_io import process_rgb_image
    from ce_scheme3.reference_model import ContrastConfig

    rgb = np.array(
        [[[0, 0, 0], [32, 32, 32]], [[128, 128, 128], [255, 255, 255]]],
        dtype=np.uint8,
    )
    result = process_rgb_image(rgb, ContrastConfig())
    assert result.enhanced_rgb.shape == rgb.shape
    assert len(result.lut) == 256
    assert "mean_value_in" in result.stats
    assert "mean_value_out" in result.stats
