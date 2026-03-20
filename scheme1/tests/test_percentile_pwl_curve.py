import pytest


def test_percentile_pwl_narrow_dynamic_range_caps_gain_and_expands_anchor_span():
    from ce_scheme1.percentile_pwl import FloatPercentilePwlConfig, FloatPercentilePwlModel

    frame = [120] * 64 + [122] * 64 + [124] * 64
    cfg = FloatPercentilePwlConfig(
        alpha_num=1,
        alpha_den=1,
        gain_min=0.8,
        gain_max=2.0,
        toe_margin=16.0,
        shoulder_margin=16.0,
    )
    model = FloatPercentilePwlModel(cfg)

    result = model.process_frame(frame)

    assert result.stats["gain_nominal"] > cfg.gain_max
    assert result.stats["gain"] == pytest.approx(cfg.gain_max)
    assert result.stats["anchor_low"] <= result.stats["p_low"]
    assert result.stats["anchor_high"] >= result.stats["p_high"]
    assert result.stats["anchor_high"] - result.stats["anchor_low"] >= result.stats["p_high"] - result.stats["p_low"]


def test_percentile_pwl_gain_matches_formula_from_resolved_anchors():
    from ce_scheme1.percentile_pwl import (
        FloatPercentilePwlConfig,
        _resolve_anchor_span,
    )

    cfg = FloatPercentilePwlConfig(gain_min=0.5, gain_max=3.0, toe_margin=12.0, shoulder_margin=20.0)
    anchor_low, anchor_high, gain_nominal, gain = _resolve_anchor_span(48.0, 176.0, cfg)
    y_low = cfg.toe_margin
    y_high = cfg.input_max - cfg.shoulder_margin
    expected = (y_high - y_low) / (anchor_high - anchor_low)

    assert gain_nominal == pytest.approx((y_high - y_low) / (176.0 - 48.0))
    assert gain == pytest.approx(expected)


def test_percentile_pwl_knots_hit_expected_anchor_outputs():
    from ce_scheme1.percentile_pwl import (
        FloatPercentilePwlConfig,
        _build_anchor_pwl_knots,
        _expand_pwl_curve,
    )

    cfg = FloatPercentilePwlConfig(toe_margin=10.0, shoulder_margin=14.0)
    knots = _build_anchor_pwl_knots(40.0, 180.0, cfg)
    curve = _expand_pwl_curve(knots, cfg)

    assert len(knots) == 4
    assert knots[0] == (0, 0.0)
    assert knots[1] == (40, pytest.approx(cfg.toe_margin))
    assert knots[2] == (180, pytest.approx(cfg.input_max - cfg.shoulder_margin))
    assert knots[-1] == (255, float(cfg.input_max))
    assert curve[40] == pytest.approx(cfg.toe_margin)
    assert curve[180] == pytest.approx(cfg.input_max - cfg.shoulder_margin)


def test_percentile_pwl_output_lut_is_bounded_and_monotonic():
    from ce_scheme1.percentile_pwl import FloatPercentilePwlConfig, FloatPercentilePwlModel

    model = FloatPercentilePwlModel(FloatPercentilePwlConfig(alpha_num=1, alpha_den=1))
    result = model.process_frame([32] * 50 + [96] * 100 + [160] * 50)

    assert min(result.lut) >= 0
    assert max(result.lut) <= 255
    assert all(a <= b for a, b in zip(result.lut, result.lut[1:]))
