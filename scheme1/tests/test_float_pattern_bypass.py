import numpy as np
from ce_scheme1.percentile_pwl import FloatPercentilePwlConfig, FloatPercentilePwlModel


def test_pattern_bypass_detects_dense_gradient():
    model = FloatPercentilePwlModel(FloatPercentilePwlConfig(pattern_bypass_enable=True))
    # Dense gradient: 256 unique values, spans the whole range
    ramp = np.tile(np.arange(256, dtype=np.uint8), (32, 1)).reshape(-1).tolist()
    result = model.process_frame(ramp)
    
    assert result.stats["pattern_bypass"] is True
    assert result.stats["pattern_bypass_reason"] == "dense_gradient"
    # Identity curve
    assert np.allclose(result.tone_curve, np.arange(256))


def test_pattern_bypass_detects_sparse_pattern():
    model = FloatPercentilePwlModel()
    # Sparse pattern: 4 distinct colors, 25% each (max_bin = 25%, <= 40% threshold)
    blocks = np.repeat(np.arange(4, dtype=np.uint8) * 85, 256 // 4)
    plane = np.tile(blocks, (32, 1)).reshape(-1).tolist()
    result = model.process_frame(plane)
    
    assert result.stats["pattern_bypass"] is True
    assert result.stats["pattern_bypass_reason"] == "sparse_pattern"
    assert np.allclose(result.tone_curve, np.arange(256))


def test_pattern_bypass_detects_comb_pattern():
    model = FloatPercentilePwlModel()
    # Comb pattern: discrete steps with holes (like concentric boxes or step wedge)
    # Using 16 distinct levels with equal spacing (15 holes)
    boxes = np.zeros((256,), dtype=np.uint8)
    for i in range(16):
        boxes[i*16:(i+1)*16] = int(i * 255 / 15)
    plane = np.tile(boxes, (32, 1)).reshape(-1).tolist()
    result = model.process_frame(plane)
    
    assert result.stats["pattern_bypass"] is True
    assert result.stats["pattern_bypass_reason"] == "comb_pattern"
    assert np.allclose(result.tone_curve, np.arange(256))


def test_pattern_bypass_ignores_natural_like_image():
    model = FloatPercentilePwlModel(FloatPercentilePwlConfig(enable_temporal_smoothing=False))
    # Natural-like image: gradient with random noise (dense, but too many runs/holes)
    base = np.linspace(96, 224, 256, dtype=np.uint8)
    rng = np.random.default_rng(42)
    noise = rng.integers(-5, 6, size=256, endpoint=True)
    textured = np.clip(base + noise, 0, 255).astype(np.uint8)
    plane = np.tile(textured, (32, 1)).reshape(-1).tolist()
    result = model.process_frame(plane)
    
    assert result.stats["pattern_bypass"] is False
    assert result.stats["pattern_bypass_reason"] == ""
    # Should not be identity
    assert not np.allclose(result.tone_curve, np.arange(256))


def test_pattern_bypass_can_be_disabled():
    model = FloatPercentilePwlModel(FloatPercentilePwlConfig(pattern_bypass_enable=False, enable_temporal_smoothing=False))
    # Dense gradient: would normally bypass
    ramp = np.tile(np.arange(256, dtype=np.uint8), (32, 1)).reshape(-1).tolist()
    result = model.process_frame(ramp)
    
    assert result.stats["pattern_bypass"] is False
    assert result.stats["pattern_bypass_reason"] == ""
    # Should not be identity because bypass is disabled
    assert not np.allclose(result.tone_curve, np.arange(256))
