# DDIC Image Batch Evaluator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a `self-LUT` image batch evaluator on top of the DDIC contrast reference model so real images can be processed offline and exported with LUT/stat metadata.

**Architecture:** Keep the current algorithm core in `reference_model.py`, add a small image-processing layer for RGB/luma conversion and LUT application, then add a batch runner that scans a directory and writes enhanced images plus metadata. The first version supports only per-image self-LUT processing and avoids sequence/video behavior.

**Tech Stack:** Python 3.12, `pytest`, `numpy`, `Pillow`, standard library

---

### Task 1: Add Image-Luma Conversion Primitives

**Files:**
- Create: `src/ddic_ce/image_io.py`
- Create: `tests/test_image_io.py`

**Step 1: Write the failing test**

```python
import numpy as np

from ddic_ce.image_io import rgb_to_luma


def test_rgb_to_luma_returns_uint8_plane_with_same_height_width():
    rgb = np.array([[[0, 0, 0], [255, 255, 255]]], dtype=np.uint8)
    y = rgb_to_luma(rgb)
    assert y.shape == (1, 2)
    assert y.dtype == np.uint8
    assert int(y[0, 0]) == 0
    assert int(y[0, 1]) == 255
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_image_io.py::test_rgb_to_luma_returns_uint8_plane_with_same_height_width -v`
Expected: FAIL with `ModuleNotFoundError` or missing symbol error.

**Step 3: Write minimal implementation**

```python
def rgb_to_luma(rgb):
    ...
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_image_io.py::test_rgb_to_luma_returns_uint8_plane_with_same_height_width -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_image_io.py src/ddic_ce/image_io.py
git commit -m "feat: add image luma conversion helpers"
```

### Task 2: Add LUT Application Back to RGB

**Files:**
- Modify: `src/ddic_ce/image_io.py`
- Modify: `tests/test_image_io.py`

**Step 1: Write the failing test**

```python
import numpy as np

from ddic_ce.image_io import apply_luma_lut_to_rgb


def test_apply_luma_lut_to_rgb_preserves_shape_and_uint8_range():
    rgb = np.array([[[10, 20, 30], [100, 120, 140]]], dtype=np.uint8)
    lut = list(range(256))
    out = apply_luma_lut_to_rgb(rgb, lut)
    assert out.shape == rgb.shape
    assert out.dtype == np.uint8
    assert int(out.min()) >= 0
    assert int(out.max()) <= 255
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_image_io.py::test_apply_luma_lut_to_rgb_preserves_shape_and_uint8_range -v`
Expected: FAIL with missing function error.

**Step 3: Write minimal implementation**

```python
def apply_luma_lut_to_rgb(rgb, lut):
    ...
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_image_io.py::test_apply_luma_lut_to_rgb_preserves_shape_and_uint8_range -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_image_io.py src/ddic_ce/image_io.py
git commit -m "feat: apply luma LUT to RGB images"
```

### Task 3: Add Single-Image Processing API

**Files:**
- Modify: `src/ddic_ce/image_io.py`
- Modify: `src/ddic_ce/__init__.py`
- Modify: `tests/test_image_io.py`

**Step 1: Write the failing test**

```python
import numpy as np

from ddic_ce.image_io import process_rgb_image
from ddic_ce.reference_model import ContrastConfig


def test_process_rgb_image_returns_enhanced_rgb_lut_and_stats():
    rgb = np.array(
        [[[0, 0, 0], [32, 32, 32]], [[128, 128, 128], [255, 255, 255]]],
        dtype=np.uint8,
    )
    result = process_rgb_image(rgb, ContrastConfig())
    assert result.enhanced_rgb.shape == rgb.shape
    assert len(result.lut) == 256
    assert "mean_in" in result.stats
    assert "mean_out" in result.stats
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_image_io.py::test_process_rgb_image_returns_enhanced_rgb_lut_and_stats -v`
Expected: FAIL with missing symbol error.

**Step 3: Write minimal implementation**

```python
def process_rgb_image(rgb, cfg):
    ...
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_image_io.py::test_process_rgb_image_returns_enhanced_rgb_lut_and_stats -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_image_io.py src/ddic_ce/image_io.py src/ddic_ce/__init__.py
git commit -m "feat: add single-image DDIC batch evaluation API"
```

### Task 4: Add Directory Batch Runner

**Files:**
- Create: `src/ddic_ce/batch_runner.py`
- Create: `tests/test_batch_runner.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

import numpy as np
from PIL import Image

from ddic_ce.batch_runner import run_batch
from ddic_ce.reference_model import ContrastConfig


def test_run_batch_writes_enhanced_images_and_summary(tmp_path: Path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    img = np.array([[[0, 0, 0], [255, 255, 255]]], dtype=np.uint8)
    Image.fromarray(img, mode="RGB").save(input_dir / "sample.png")

    run_batch(input_dir, output_dir, ContrastConfig())

    assert (output_dir / "enhanced" / "sample.png").exists()
    assert (output_dir / "lut" / "sample.csv").exists()
    assert (output_dir / "meta" / "sample.json").exists()
    assert (output_dir / "summary.csv").exists()
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_batch_runner.py::test_run_batch_writes_enhanced_images_and_summary -v`
Expected: FAIL with `ModuleNotFoundError` or missing symbol error.

**Step 3: Write minimal implementation**

```python
def run_batch(input_dir, output_dir, cfg):
    ...
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_batch_runner.py::test_run_batch_writes_enhanced_images_and_summary -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_batch_runner.py src/ddic_ce/batch_runner.py
git commit -m "feat: add DDIC image batch evaluator"
```

### Task 5: Add CLI Entry and Full Verification

**Files:**
- Modify: `src/ddic_ce/batch_runner.py`
- Modify: `src/ddic_ce/__init__.py`
- Modify: `tests/test_batch_runner.py`

**Step 1: Write the failing test**

```python
from ddic_ce.batch_runner import build_arg_parser


def test_build_arg_parser_accepts_required_paths():
    parser = build_arg_parser()
    args = parser.parse_args(["in_dir", "out_dir"])
    assert args.input_dir == "in_dir"
    assert args.output_dir == "out_dir"
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_batch_runner.py::test_build_arg_parser_accepts_required_paths -v`
Expected: FAIL with missing function error.

**Step 3: Write minimal implementation**

```python
def build_arg_parser():
    ...
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_batch_runner.py::test_build_arg_parser_accepts_required_paths -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_batch_runner.py src/ddic_ce/batch_runner.py src/ddic_ce/__init__.py
git commit -m "feat: expose CLI for DDIC image batch evaluator"
```
