import pytest


def test_percentile_pwl_empty_frame_after_valid_frame_uses_previous_lut():
    from ce_scheme1.percentile_pwl import FloatPercentilePwlConfig, FloatPercentilePwlModel

    model = FloatPercentilePwlModel(FloatPercentilePwlConfig(alpha_num=1, alpha_den=2))
    previous = model.process_frame([24, 32, 48, 64, 96, 128, 192])
    empty = model.process_frame([])

    assert empty.lut == previous.lut


def test_percentile_pwl_second_frame_reports_smaller_step_with_iir_than_without():
    from ce_scheme1.percentile_pwl import FloatPercentilePwlConfig, FloatPercentilePwlModel

    first = [32] * 64 + [128] * 64 + [196] * 64
    second = [40] * 64 + [136] * 64 + [204] * 64

    smooth_cfg = FloatPercentilePwlConfig(alpha_num=1, alpha_den=4, enable_temporal_smoothing=True, pattern_bypass_enable=False)
    raw_cfg = FloatPercentilePwlConfig(alpha_num=1, alpha_den=4, enable_temporal_smoothing=False, pattern_bypass_enable=False)

    smooth_model = FloatPercentilePwlModel(smooth_cfg)
    raw_model = FloatPercentilePwlModel(raw_cfg)

    smooth_first = smooth_model.process_frame(first)
    raw_first = raw_model.process_frame(first)
    smooth_second = smooth_model.process_frame(second)
    raw_second = raw_model.process_frame(second)

    smooth_delta = sum(abs(a - b) for a, b in zip(smooth_first.lut, smooth_second.lut))
    raw_delta = sum(abs(a - b) for a, b in zip(raw_first.lut, raw_second.lut))

    assert smooth_delta < raw_delta


def test_percentile_pwl_reports_gain_fields_in_stats():
    from ce_scheme1.percentile_pwl import FloatPercentilePwlConfig, FloatPercentilePwlModel

    model = FloatPercentilePwlModel(FloatPercentilePwlConfig(alpha_num=1, alpha_den=1, pattern_bypass_enable=False))
    result = model.process_frame([48] * 64 + [96] * 64 + [160] * 64)

    assert result.stats["gain_nominal"] >= 0.0
    assert result.stats["gain"] >= 0.0
    assert result.stats["anchor_high"] >= result.stats["anchor_low"]
