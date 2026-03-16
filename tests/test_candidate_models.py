from ddic_ce.reference_model import ContrastConfig, ContrastReferenceModel


def test_adaptive_gamma_model_matches_baseline_output_contract():
    from ddic_ce.candidate_models import AdaptiveGammaConfig, AdaptiveGammaReferenceModel

    cfg = AdaptiveGammaConfig(alpha_num=1, alpha_den=1)
    model = AdaptiveGammaReferenceModel(cfg)
    frame = [0, 12, 24, 48, 96, 192, 255]

    result = model.process_frame(frame)

    assert len(result.histogram) == cfg.n_bins
    assert len(result.lut) == cfg.lut_size
    assert len(result.mapped_samples) == len(frame)
    assert all(a <= b for a, b in zip(result.lut, result.lut[1:]))


def test_adaptive_gamma_branch_lifts_dark_scene_more_than_baseline():
    from ddic_ce.candidate_models import AdaptiveGammaConfig, AdaptiveGammaReferenceModel

    frame = [4, 8, 12, 16, 24, 32, 48, 64]
    base_result = ContrastReferenceModel(ContrastConfig(alpha_num=1, alpha_den=1)).process_frame(frame)
    adaptive_result = AdaptiveGammaReferenceModel(
        AdaptiveGammaConfig(alpha_num=1, alpha_den=1, gamma_gain=0.8, gamma_blend=0.7)
    ).process_frame(frame)

    assert adaptive_result.lut[32] >= base_result.lut[32]
    assert adaptive_result.lut[64] >= base_result.lut[64]


def test_discrete_scene_model_classifies_expected_scene_without_hold():
    from ddic_ce.candidate_models import DiscreteSceneGainConfig, DiscreteSceneGainModel

    cfg = DiscreteSceneGainConfig(scene_hold_enable=False)
    model = DiscreteSceneGainModel(cfg)

    bright = [200] * 82 + [224] * 18
    dark_i = [16] * 60 + [128] * 40
    dark_ii = [0] * 90 + [8] * 10
    normal = [96] * 50 + [160] * 50
    flat = [80] * 100

    assert model.process_frame(bright).scene_name == "Bright"
    assert model.process_frame(dark_i).scene_name == "Dark I"
    assert model.process_frame(dark_ii).scene_name == "Dark II"
    assert model.process_frame(normal).scene_name == "Normal"
    assert model.process_frame(flat).bypass_flag is True


def test_discrete_scene_model_emits_monotonic_tone_lut_and_bounded_gain_lut():
    from ddic_ce.candidate_models import DiscreteSceneGainConfig, DiscreteSceneGainModel

    model = DiscreteSceneGainModel(DiscreteSceneGainConfig(scene_hold_enable=False))
    result = model.process_frame([16, 24, 32, 48, 64, 96, 128, 192, 224])

    assert len(result.lut) == 256
    assert len(result.gain_lut) == 256
    assert result.gain_lut[0] == 0
    assert all(a <= b for a, b in zip(result.lut, result.lut[1:]))
    assert min(result.gain_lut) >= 0
    assert max(result.gain_lut) <= 1792


def test_discrete_scene_model_holds_scene_until_second_confirmation():
    from ddic_ce.candidate_models import DiscreteSceneGainConfig, DiscreteSceneGainModel

    model = DiscreteSceneGainModel(DiscreteSceneGainConfig())
    normal = [120] * 50 + [180] * 50
    bright = [168] * 82 + [224] * 18

    first = model.process_frame(normal)
    second = model.process_frame(bright)
    third = model.process_frame(bright)

    assert first.scene_name == "Normal"
    assert second.raw_scene_name == "Bright"
    assert second.scene_name == "Normal"
    assert third.scene_name == "Bright"


def test_discrete_scene_model_outputs_gain_only_when_cabc_or_aie_enabled():
    from ddic_ce.candidate_models import DiscreteSceneGainConfig, DiscreteSceneGainModel

    model = DiscreteSceneGainModel(DiscreteSceneGainConfig(scene_hold_enable=False))
    rgb_frame = [(32, 32, 32), (64, 48, 32), (96, 96, 96)]

    result = model.process_rgb_frame(rgb_frame, cabc_enabled=True, aie_enabled=False)

    assert result.gain_mode_enabled is True
    assert result.rgb_out is None
    assert len(result.gain_samples) == len(rgb_frame)
    assert all(gain >= 0 for gain in result.gain_samples)


def test_discrete_scene_model_multiplies_rgb_when_local_ce_mode_is_enabled():
    from ddic_ce.candidate_models import DiscreteSceneGainConfig, DiscreteSceneGainModel

    model = DiscreteSceneGainModel(DiscreteSceneGainConfig(scene_hold_enable=False))
    rgb_frame = [(32, 32, 32), (64, 48, 32), (96, 96, 96)]

    result = model.process_rgb_frame(rgb_frame, cabc_enabled=False, aie_enabled=False)

    assert result.gain_mode_enabled is False
    assert result.rgb_out is not None
    expected_first = tuple(min(255, (channel * result.gain_samples[0]) >> 10) for channel in rgb_frame[0])
    assert result.rgb_out[0] == expected_first


def test_discrete_scene_model_normalizes_10bit_rgb_to_8bit_luma_stats():
    from ddic_ce.candidate_models import DiscreteSceneGainConfig, DiscreteSceneGainModel

    model = DiscreteSceneGainModel(DiscreteSceneGainConfig(input_bit_depth=10, scene_hold_enable=False))
    rgb_frame = [(0, 0, 0), (1023, 1023, 1023), (512, 512, 512)]

    result = model.process_rgb_frame(rgb_frame, cabc_enabled=True, aie_enabled=False)

    assert result.stats["min_luma"] == 0.0
    assert result.stats["max_luma"] == 255.0
    assert 120.0 <= result.stats["mean"] <= 135.0
