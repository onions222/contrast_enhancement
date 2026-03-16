# DDIC Contrast Reference Model Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python reference model for the V1 DDIC contrast enhancement algorithm using `32/64`-bin clip-limited CDF and frame-to-frame LUT smoothing.

**Architecture:** The reference model will expose a small stateless API for one-frame histogram analysis and LUT generation, plus a small stateful wrapper that carries the previous LUT across frames. The implementation stays close to the handoff document: histogram accumulation, bin smoothing, clip-and-redistribute, CDF-to-LUT expansion, LUT IIR, and monotonic clamp.

**Tech Stack:** Python 3.12, `pytest`, standard library only

---

### Task 1: Scaffold the Reference Model Module

**Files:**
- Create: `src/ddic_ce/__init__.py`
- Create: `src/ddic_ce/reference_model.py`
- Test: `tests/test_reference_model.py`

**Step 1: Write the failing test**

```python
from ddic_ce.reference_model import ContrastConfig


def test_default_config_uses_v1_defaults():
    cfg = ContrastConfig()
    assert cfg.n_bins == 32
    assert cfg.lut_size == 256
    assert cfg.alpha_num == 1
    assert cfg.alpha_den == 8
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_reference_model.py::test_default_config_uses_v1_defaults -v`
Expected: FAIL with `ModuleNotFoundError` or missing symbol error.

**Step 3: Write minimal implementation**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ContrastConfig:
    n_bins: int = 32
    lut_size: int = 256
    alpha_num: int = 1
    alpha_den: int = 8
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_reference_model.py::test_default_config_uses_v1_defaults -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_reference_model.py src/ddic_ce/__init__.py src/ddic_ce/reference_model.py
git commit -m "feat: scaffold DDIC contrast reference model"
```

### Task 2: Add Histogram and Clip-Redistribute Primitives

**Files:**
- Modify: `src/ddic_ce/reference_model.py`
- Modify: `tests/test_reference_model.py`

**Step 1: Write the failing test**

```python
from ddic_ce.reference_model import ContrastConfig, compute_histogram, clip_and_redistribute


def test_compute_histogram_counts_bins_for_8bit_samples():
    cfg = ContrastConfig(n_bins=32)
    samples = [0, 7, 8, 63, 64, 127, 128, 255]
    hist = compute_histogram(samples, cfg)
    assert sum(hist) == len(samples)
    assert hist[0] == 3
    assert hist[7] == 1
    assert hist[8] == 1
    assert hist[15] == 1
    assert hist[16] == 1
    assert hist[31] == 1


def test_clip_and_redistribute_preserves_total_count():
    hist = [10, 0, 0, 0]
    clipped = clip_and_redistribute(hist, clip_limit=4)
    assert sum(clipped) == sum(hist)
    assert max(clipped) <= 6
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_reference_model.py::test_compute_histogram_counts_bins_for_8bit_samples tests/test_reference_model.py::test_clip_and_redistribute_preserves_total_count -v`
Expected: FAIL with missing function errors.

**Step 3: Write minimal implementation**

```python
def compute_histogram(samples, cfg):
    ...


def clip_and_redistribute(hist, clip_limit):
    ...
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_reference_model.py::test_compute_histogram_counts_bins_for_8bit_samples tests/test_reference_model.py::test_clip_and_redistribute_preserves_total_count -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_reference_model.py src/ddic_ce/reference_model.py
git commit -m "feat: add histogram primitives for contrast reference model"
```

### Task 3: Generate a Monotonic LUT from Histogram Statistics

**Files:**
- Modify: `src/ddic_ce/reference_model.py`
- Modify: `tests/test_reference_model.py`

**Step 1: Write the failing test**

```python
from ddic_ce.reference_model import ContrastConfig, generate_lut_from_histogram


def test_generate_lut_returns_monotonic_full_range_mapping():
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
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_reference_model.py::test_generate_lut_returns_monotonic_full_range_mapping -v`
Expected: FAIL with missing function error.

**Step 3: Write minimal implementation**

```python
def generate_lut_from_histogram(hist, total_pixels, prev_lut, cfg):
    ...
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_reference_model.py::test_generate_lut_returns_monotonic_full_range_mapping -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_reference_model.py src/ddic_ce/reference_model.py
git commit -m "feat: generate monotonic LUT for contrast reference model"
```

### Task 4: Add Frame-to-Frame State and End-to-End API

**Files:**
- Modify: `src/ddic_ce/reference_model.py`
- Modify: `src/ddic_ce/__init__.py`
- Modify: `tests/test_reference_model.py`

**Step 1: Write the failing test**

```python
from ddic_ce.reference_model import ContrastConfig, ContrastReferenceModel


def test_model_process_frame_returns_smoothed_lut_and_mapped_samples():
    cfg = ContrastConfig()
    model = ContrastReferenceModel(cfg)
    frame = [0, 16, 32, 64, 128, 192, 255]
    result = model.process_frame(frame)
    assert len(result.lut) == cfg.lut_size
    assert len(result.mapped_samples) == len(frame)
    assert all(a <= b for a, b in zip(result.lut, result.lut[1:]))
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_reference_model.py::test_model_process_frame_returns_smoothed_lut_and_mapped_samples -v`
Expected: FAIL with missing class or method error.

**Step 3: Write minimal implementation**

```python
class ContrastReferenceModel:
    ...
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_reference_model.py::test_model_process_frame_returns_smoothed_lut_and_mapped_samples -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_reference_model.py src/ddic_ce/__init__.py src/ddic_ce/reference_model.py
git commit -m "feat: add end-to-end DDIC contrast reference model"
```
