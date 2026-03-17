from ddic_ce.candidate_models import DiscreteSceneGainConfig, DiscreteSceneGainModel


def test_float_scene_model_matches_scene_decisions_of_integer_model():
    from ddic_ce_float.discrete_scene_gain import FloatDiscreteSceneGainConfig, FloatDiscreteSceneGainModel

    frame = [168] * 82 + [224] * 18
    int_model = DiscreteSceneGainModel(DiscreteSceneGainConfig(scene_hold_enable=False))
    float_model = FloatDiscreteSceneGainModel(FloatDiscreteSceneGainConfig(scene_hold_enable=False))

    int_result = int_model.process_frame(frame)
    float_result = float_model.process_frame(frame)

    assert float_result.scene_name == int_result.scene_name
    assert float_result.raw_scene_name == int_result.raw_scene_name
    assert float_result.bypass_flag is False


def test_float_scene_model_emits_float_gain_lut_and_monotonic_tone_curve():
    from ddic_ce_float.discrete_scene_gain import FloatDiscreteSceneGainConfig, FloatDiscreteSceneGainModel

    model = FloatDiscreteSceneGainModel(FloatDiscreteSceneGainConfig(scene_hold_enable=False))
    result = model.process_frame([16, 24, 32, 48, 64, 96, 128, 192, 224])

    assert len(result.tone_curve) == 256
    assert len(result.gain_lut) == 256
    assert result.gain_lut[0] == 0.0
    assert all(a <= b for a, b in zip(result.tone_curve, result.tone_curve[1:]))
    assert min(result.gain_lut) >= 0.0
    assert max(result.gain_lut) <= 1.75


def test_float_scene_model_config_matches_revised_curve_families():
    from ddic_ce_float.discrete_scene_gain import FloatDiscreteSceneGainConfig, FloatDiscreteSceneGainModel

    cfg = FloatDiscreteSceneGainConfig(scene_hold_enable=False)
    model = FloatDiscreteSceneGainModel(cfg)

    assert cfg.family_b_knots == ((0, 0), (96, 64), (192, 192), (224, 236), (255, 255))
    assert cfg.family_d_knots == ((0, 0), (48, 24), (96, 144), (192, 232), (255, 255))
    assert model._scene_tone_curves[1][192] == 192.0
    assert model._scene_tone_curves[1][224] > 224.0


def test_float_scene_model_outputs_gain_only_or_rgb_by_mode():
    from ddic_ce_float.discrete_scene_gain import FloatDiscreteSceneGainConfig, FloatDiscreteSceneGainModel

    model = FloatDiscreteSceneGainModel(FloatDiscreteSceneGainConfig(scene_hold_enable=False))
    rgb_frame = [(32, 32, 32), (64, 48, 32), (96, 96, 96)]

    gain_result = model.process_rgb_frame(rgb_frame, cabc_enabled=True, aie_enabled=False)
    rgb_result = model.process_rgb_frame(rgb_frame, cabc_enabled=False, aie_enabled=False)

    assert gain_result.gain_mode_enabled is True
    assert gain_result.rgb_out is None
    assert rgb_result.gain_mode_enabled is False
    assert rgb_result.rgb_out is not None
    assert rgb_result.rgb_out[0][0] == rgb_frame[0][0] * rgb_result.gain_samples[0]


def test_float_scene_model_normalizes_10bit_rgb_to_8bit_luma_domain():
    from ddic_ce_float.discrete_scene_gain import FloatDiscreteSceneGainConfig, FloatDiscreteSceneGainModel

    model = FloatDiscreteSceneGainModel(FloatDiscreteSceneGainConfig(input_bit_depth=10, scene_hold_enable=False))
    rgb_frame = [(0, 0, 0), (1023, 1023, 1023), (512, 512, 512)]

    result = model.process_rgb_frame(rgb_frame, cabc_enabled=True, aie_enabled=False)

    assert result.stats["min_luma"] == 0.0
    assert result.stats["max_luma"] == 255.0
    assert 120.0 <= result.stats["mean"] <= 135.0
