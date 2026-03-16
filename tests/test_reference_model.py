from ddic_ce.reference_model import ContrastConfig


def test_default_config_uses_v1_defaults():
    cfg = ContrastConfig()
    assert cfg.n_bins == 32
    assert cfg.lut_size == 256
    assert cfg.alpha_num == 1
    assert cfg.alpha_den == 8


def test_compute_histogram_counts_bins_for_8bit_samples():
    from ddic_ce.reference_model import compute_histogram

    cfg = ContrastConfig(n_bins=32)
    samples = [0, 7, 8, 63, 64, 127, 128, 255]
    hist = compute_histogram(samples, cfg)
    assert sum(hist) == len(samples)
    assert hist[0] == 2
    assert hist[1] == 1
    assert hist[7] == 1
    assert hist[8] == 1
    assert hist[15] == 1
    assert hist[16] == 1
    assert hist[31] == 1


def test_clip_and_redistribute_preserves_total_count():
    from ddic_ce.reference_model import clip_and_redistribute

    hist = [10, 0, 0, 0]
    clipped = clip_and_redistribute(hist, clip_limit=4)
    assert sum(clipped) == sum(hist)
    assert max(clipped) <= 6


def test_generate_lut_returns_monotonic_full_range_mapping():
    from ddic_ce.reference_model import generate_lut_from_histogram

    cfg = ContrastConfig(n_bins=32, lut_size=256, alpha_num=1, alpha_den=1)
    hist = [0] * 32
    hist[8] = 8
    hist[16] = 8
    hist[24] = 8
    lut = generate_lut_from_histogram(hist, total_pixels=24, prev_lut=None, cfg=cfg)
    assert len(lut) == 256
    assert lut[0] <= lut[-1]
    assert all(a <= b for a, b in zip(lut, lut[1:]))
    assert 0 <= min(lut)
    assert max(lut) <= 255


def test_model_process_frame_returns_smoothed_lut_and_mapped_samples():
    from ddic_ce.reference_model import ContrastReferenceModel

    cfg = ContrastConfig()
    model = ContrastReferenceModel(cfg)
    frame = [0, 16, 32, 64, 128, 192, 255]
    result = model.process_frame(frame)
    assert len(result.lut) == cfg.lut_size
    assert len(result.mapped_samples) == len(frame)
    assert all(a <= b for a, b in zip(result.lut, result.lut[1:]))


def test_default_config_exposes_experiment_controls():
    cfg = ContrastConfig()

    assert cfg.dark_percentile == 2.0
    assert cfg.bright_percentile == 98.0
    assert cfg.shadow_boost == 0.0
    assert cfg.highlight_suppress == 0.0


def test_shadow_boost_raises_low_end_of_generated_lut():
    from ddic_ce.reference_model import generate_lut_from_histogram

    hist = [0] * 32
    hist[1] = 32
    hist[2] = 16
    base_cfg = ContrastConfig(alpha_num=1, alpha_den=1, shadow_boost=0.0)
    boost_cfg = ContrastConfig(alpha_num=1, alpha_den=1, shadow_boost=0.3)

    base_lut = generate_lut_from_histogram(hist, total_pixels=48, prev_lut=None, cfg=base_cfg)
    boost_lut = generate_lut_from_histogram(hist, total_pixels=48, prev_lut=None, cfg=boost_cfg)

    assert boost_lut[24] > base_lut[24]
    assert all(a <= b for a, b in zip(boost_lut, boost_lut[1:]))


def test_highlight_suppress_lowers_high_end_of_generated_lut():
    from ddic_ce.reference_model import generate_lut_from_histogram

    hist = [0] * 32
    hist[27] = 16
    hist[29] = 32
    base_cfg = ContrastConfig(alpha_num=1, alpha_den=1, highlight_suppress=0.0)
    suppress_cfg = ContrastConfig(alpha_num=1, alpha_den=1, highlight_suppress=0.35)

    base_lut = generate_lut_from_histogram(hist, total_pixels=48, prev_lut=None, cfg=base_cfg)
    suppress_lut = generate_lut_from_histogram(hist, total_pixels=48, prev_lut=None, cfg=suppress_cfg)

    assert suppress_lut[224] < base_lut[224]
    assert all(a <= b for a, b in zip(suppress_lut, suppress_lut[1:]))
