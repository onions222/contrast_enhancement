import numpy as np


def test_generate_ramp_pattern_spans_requested_range():
    from ce_scheme3.patterns import generate_ramp_pattern

    ramp = generate_ramp_pattern(width=8, height=2, start=10, stop=210)

    assert ramp.shape == (2, 8)
    assert ramp.dtype == np.uint8
    assert int(ramp[0, 0]) == 10
    assert int(ramp[0, -1]) == 210


def test_generate_bimodal_pattern_contains_two_primary_levels():
    from ce_scheme3.patterns import generate_bimodal_pattern

    bimodal = generate_bimodal_pattern(width=8, height=4, low=24, high=200)
    unique = set(np.unique(bimodal).tolist())

    assert unique == {24, 200}


def test_generate_noise_on_dark_pattern_is_deterministic():
    from ce_scheme3.patterns import generate_noise_on_dark_pattern

    first = generate_noise_on_dark_pattern(width=8, height=8, base=12, noise_amplitude=6, seed=7)
    second = generate_noise_on_dark_pattern(width=8, height=8, base=12, noise_amplitude=6, seed=7)

    assert np.array_equal(first, second)
    assert int(first.min()) >= 12
    assert int(first.max()) <= 18


def test_generate_skin_tone_patch_pattern_returns_expected_bands():
    from ce_scheme3.patterns import generate_skin_tone_patch_pattern

    pattern = generate_skin_tone_patch_pattern(width=6, height=4, background=96, patch=172)

    assert pattern.shape == (4, 6)
    assert set(np.unique(pattern).tolist()) == {96, 172}


def test_generate_pattern_suite_provides_named_metadata_and_planes():
    from ce_scheme3.patterns import generate_pattern_suite

    suite = generate_pattern_suite(width=8, height=8)

    assert "ramp" in suite
    assert "noise_on_dark" in suite
    assert suite["ramp"]["plane"].shape == (8, 8)
    assert suite["ramp"]["metadata"]["pattern"] == "ramp"
    assert suite["noise_on_dark"]["metadata"]["seed"] == 13
