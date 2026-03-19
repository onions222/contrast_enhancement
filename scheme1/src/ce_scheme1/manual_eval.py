from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ce_scheme1.image_io import rgb_to_luma
from ce_scheme1.metrics import summarize_plane
from ce_scheme1.percentile_pwl import FloatPercentilePwlConfig, FloatPercentilePwlModel
from ce_scheme1.temporal_runner import SUPPORTED_EXTENSIONS


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT_DIR = REPO_ROOT / "data" / "derived" / "eval_subsets"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "derived" / "scheme1_manual_eval"


@dataclass(frozen=True)
class FloatManualEvalConfig:
    input_dir: Path = DEFAULT_INPUT_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    recursive: bool = True


def _iter_image_paths(input_dir: Path, recursive: bool) -> list[Path]:
    if not input_dir.exists():
        return []
    iterator = input_dir.rglob("*") if recursive else input_dir.iterdir()
    return sorted(path for path in iterator if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS)


def run_float_manual_eval(cfg: FloatManualEvalConfig | None = None) -> dict[str, object]:
    config = cfg or FloatManualEvalConfig()
    model = FloatPercentilePwlModel(FloatPercentilePwlConfig())
    output_dir = Path(config.output_dir)
    enhanced_dir = output_dir / "enhanced"
    meta_dir = output_dir / "meta"
    enhanced_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    frames: list[dict[str, object]] = []
    for index, image_path in enumerate(_iter_image_paths(config.input_dir, config.recursive)):
        rgb = np.asarray(Image.open(image_path).convert("RGB"), dtype=np.uint8)
        plane = rgb_to_luma(rgb)
        result = model.process_plane_image(plane)
        enhanced = np.asarray(result.mapped_samples, dtype=np.uint8).reshape(plane.shape)
        frame_summary = {
            "index": index,
            "name": image_path.name,
            "relative_path": image_path.relative_to(config.input_dir).as_posix(),
            "stats": result.stats,
            "metrics": summarize_plane(enhanced),
        }
        frames.append(frame_summary)
        Image.fromarray(enhanced).save(enhanced_dir / image_path.name)
        (meta_dir / f"{image_path.stem}.json").write_text(json.dumps(frame_summary, indent=2), encoding="utf-8")

    payload = {
        "input_dir": str(config.input_dir),
        "output_dir": str(output_dir),
        "frame_count": len(frames),
        "frames": frames,
    }
    (output_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
