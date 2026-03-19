import pytest

from ce_scheme3.discrete_scene_gain_float import FloatDiscreteSceneGainConfig
from float_scene_test_utils import make_float_model


def test_float_scene_config_contract_matches_revised_thresholds():
    cfg = FloatDiscreteSceneGainConfig()

    assert cfg.input_bit_depth == 8
    assert cfg.gain_max == pytest.approx(1.75)
    assert cfg.bypass_dynamic_range_threshold == pytest.approx(4.0)
    assert cfg.bright_mean_threshold == pytest.approx(176.0)
    assert cfg.bright_ratio_threshold == pytest.approx(0.25)
    assert cfg.dark2_mean_threshold == pytest.approx(48.0)
    assert cfg.dark2_ratio_threshold == pytest.approx(0.85)
    assert cfg.dark2_bright_ratio_threshold == pytest.approx(0.01)
    assert cfg.dark1_mean_threshold == pytest.approx(96.0)
    assert cfg.dark1_ratio_threshold == pytest.approx(0.55)
    assert cfg.scene_cut_mean_delta == pytest.approx(32.0)
    assert cfg.scene_switch_confirm_frames == 2
    assert cfg.pattern_hist_bin_count == 32
    assert cfg.pattern_dense_active_min == 14
    assert cfg.pattern_dense_span_min == 16
    assert cfg.pattern_dense_runs_max == 2
    assert cfg.pattern_dense_holes_max == 2
    assert cfg.pattern_sparse_active_max == 6
    assert cfg.pattern_sparse_peak_numer == 2
    assert cfg.pattern_sparse_peak_denom == 5
    assert cfg.pattern_comb_span_min == 10
    assert cfg.pattern_comb_runs_min == 6
    assert cfg.pattern_comb_hole_numer == 1
    assert cfg.pattern_comb_hole_denom == 3
    assert cfg.dark_ii_strength == pytest.approx(0.65)
    assert cfg.family_m_knots == ((0, 0), (64, 40), (128, 128), (192, 224), (255, 255))
    assert cfg.family_b_knots == ((0, 0), (96, 64), (192, 192), (224, 236), (255, 255))
    assert cfg.family_d_knots == ((0, 0), (48, 24), (96, 144), (192, 232), (255, 255))


def test_float_scene_curve_and_gain_snapshots_match_current_baseline():
    model = make_float_model(scene_hold_enable=False)

    normal_curve = model._scene_tone_curves[0]
    bright_curve = model._scene_tone_curves[1]
    dark_i_curve = model._scene_tone_curves[2]
    dark_ii_curve = model._scene_tone_curves[3]

    assert normal_curve[64] == pytest.approx(52.0)
    assert normal_curve[192] == pytest.approx(208.0)
    assert bright_curve[192] == pytest.approx(192.0)
    assert bright_curve[224] == pytest.approx(231.8)
    assert dark_i_curve[96] == pytest.approx(129.6)
    assert dark_i_curve[192] == pytest.approx(220.0)
    assert dark_ii_curve[64] == pytest.approx(48.4)
    assert dark_ii_curve[192] == pytest.approx(212.8)

    assert max(model._scene_gain_luts[0]) == pytest.approx(1.0833333333)
    assert max(model._scene_gain_luts[1]) == pytest.approx(1.0348214286)
    assert max(model._scene_gain_luts[2]) == pytest.approx(1.35)
    assert max(model._scene_gain_luts[3]) == pytest.approx(1.1083333333)
