import pytest

from float_scene_test_utils import make_float_model


def test_every_scene_tone_curve_is_monotonic_and_hits_identity_endpoints():
    model = make_float_model(scene_hold_enable=False)

    for curve in model._scene_tone_curves.values():
        assert curve[0] == pytest.approx(0.0)
        assert curve[255] == pytest.approx(255.0)
        assert all(left <= right for left, right in zip(curve, curve[1:]))


def test_scene_curves_follow_expected_relative_shapes():
    model = make_float_model(scene_hold_enable=False)
    normal = model._scene_tone_curves[0]
    bright = model._scene_tone_curves[1]
    dark_i = model._scene_tone_curves[2]
    dark_ii = model._scene_tone_curves[3]

    assert bright[96] < normal[96]
    assert bright[192] == pytest.approx(192.0)
    assert bright[224] > 224.0
    assert dark_i[64] >= normal[64]
    assert dark_i[96] > normal[96]
    assert dark_ii[192] > normal[192]
    assert dark_i[96] > dark_ii[96]
