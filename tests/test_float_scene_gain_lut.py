import pytest

from float_scene_test_utils import gain_smoothness_metrics, make_float_model


def test_scene_gain_luts_stay_bounded_and_non_negative():
    model = make_float_model(scene_hold_enable=False)

    for gain_lut in model._scene_gain_luts.values():
        assert gain_lut[0] == pytest.approx(0.0)
        assert min(gain_lut) >= 0.0
        assert max(gain_lut) <= model.cfg.gain_max + 1e-9


def test_scene_gain_luts_do_not_show_large_local_spikes():
    model = make_float_model(scene_hold_enable=False)

    for gain_lut in model._scene_gain_luts.values():
        first_delta, second_delta = gain_smoothness_metrics(gain_lut)
        assert first_delta <= 0.035 + 1e-9
        assert second_delta <= 0.03 + 1e-9
