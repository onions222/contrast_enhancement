from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ce_scheme3.image_io import rgb_to_value
from ce_scheme3.metrics import summarize_plane
from ce_scheme3.patterns import generate_pattern_suite
from ce_scheme3.temporal_runner import SUPPORTED_EXTENSIONS
from ce_scheme3.discrete_scene_gain_float import FloatDiscreteSceneGainConfig, FloatDiscreteSceneGainModel


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT_DIR = REPO_ROOT / "data" / "derived" / "eval_subsets"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "derived" / "float_manual_eval"
DEFAULT_MANIFEST_DIR = REPO_ROOT / "data" / "derived" / "manifests"


@dataclass(frozen=True)
class FloatManualEvalConfig:
    input_dir: Path = DEFAULT_INPUT_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    recursive: bool = True
    pattern_width: int = 256
    pattern_height: int = 256
    scene_hold_enable: bool = False
    manifest_csv: Path | None = None
    manifest_dir: Path = DEFAULT_MANIFEST_DIR


def _iter_image_paths(input_dir: Path, recursive: bool) -> list[Path]:
    if not input_dir.exists():
        return []
    iterator = input_dir.rglob("*") if recursive else input_dir.iterdir()
    return sorted(path for path in iterator if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS)


def _load_planes(cfg: FloatManualEvalConfig) -> tuple[str, list[tuple[str, str, np.ndarray]]]:
    image_paths = _iter_image_paths(cfg.input_dir, cfg.recursive)
    if image_paths:
        items: list[tuple[str, str, np.ndarray]] = []
        for image_path in image_paths:
            rgb = np.asarray(Image.open(image_path).convert("RGB"), dtype=np.uint8)
            relative_path = image_path.relative_to(cfg.input_dir).as_posix()
            safe_name = "__".join(Path(relative_path).parts)
            items.append((safe_name, relative_path, rgb_to_value(rgb)))
        return "image_directory", items

    suite = generate_pattern_suite(width=cfg.pattern_width, height=cfg.pattern_height)
    return "synthetic_patterns", [(f"{name}.png", f"{name}.png", payload["plane"]) for name, payload in suite.items()]


def _load_manifest_lookup(manifest_csv: Path | None) -> dict[str, dict[str, str]]:
    if manifest_csv is None or not Path(manifest_csv).exists():
        return {}

    lookup: dict[str, dict[str, str]] = {}
    with Path(manifest_csv).open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            relative_path = row.get("relative_path", "")
            filename = row.get("filename", "")
            if relative_path:
                lookup[relative_path] = row
            if filename and filename not in lookup:
                lookup[filename] = row
    return lookup


def _resolve_manifest_csv(cfg: FloatManualEvalConfig) -> Path | None:
    if cfg.manifest_csv is not None:
        return Path(cfg.manifest_csv)

    manifest_dir = Path(cfg.manifest_dir)
    if not manifest_dir.exists():
        return None

    candidates = sorted(manifest_dir.glob("*_manifest.csv"))
    if not candidates:
        return None
    public_first_batch = [path for path in candidates if "public_first_batch" in path.name]
    if public_first_batch:
        return sorted(public_first_batch)[-1]
    starter_synth = [path for path in candidates if "starter_synth" in path.name]
    if starter_synth:
        return sorted(starter_synth)[-1]
    return candidates[-1]


def _build_group_summary(frames: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    summary: dict[str, dict[str, object]] = {}
    for frame in frames:
        manifest = frame.get("manifest")
        group_name = manifest["scene_tag"] if isinstance(manifest, dict) and manifest.get("scene_tag") else frame["scene_name"]
        bucket = summary.setdefault(group_name, {"count": 0, "bypass_count": 0, "scene_names": {}})
        bucket["count"] += 1
        bucket["bypass_count"] += int(bool(frame["bypass_flag"]))
        bucket["scene_names"][frame["scene_name"]] = bucket["scene_names"].get(frame["scene_name"], 0) + 1
    return summary


def _build_risk_summary(frames: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    summary: dict[str, dict[str, object]] = {}
    for frame in frames:
        manifest = frame.get("manifest")
        if not isinstance(manifest, dict):
            continue
        modes = [mode for mode in str(manifest.get("expected_failure_modes", "")).split("|") if mode]
        for mode in modes:
            bucket = summary.setdefault(mode, {"count": 0, "representative_frames": []})
            bucket["count"] += 1
            if len(bucket["representative_frames"]) < 3:
                bucket["representative_frames"].append(frame["name"])
    return summary


def _write_markdown_report(output_path: Path, payload: dict[str, object]) -> None:
    lines = [
        "# Float Manual Eval Report",
        "",
        f"- Source Mode: `{payload['source_mode']}`",
        f"- Input Dir: `{payload['input_dir']}`",
        f"- Output Dir: `{payload['output_dir']}`",
        f"- Frame Count: `{payload['frame_count']}`",
        "",
        "## Scene Summary",
        "",
        "| Group | Count | Bypass Count | Output Scenes |",
        "| --- | ---: | ---: | --- |",
    ]
    for group_name, bucket in sorted(payload["group_summary"].items()):
        scene_names = ", ".join(f"{name}:{count}" for name, count in sorted(bucket["scene_names"].items()))
        lines.append(f"| {group_name} | {bucket['count']} | {bucket['bypass_count']} | {scene_names} |")

    lines.extend(
        [
            "",
            "## Risk Summary",
            "",
            "| Risk | Count | Representative Frames |",
            "| --- | ---: | --- |",
        ]
    )
    for risk_name, bucket in sorted(payload["risk_summary"].items()):
        representatives = ", ".join(bucket["representative_frames"])
        lines.append(f"| {risk_name} | {bucket['count']} | {representatives} |")

    lines.extend(
        [
            "",
            "## Representative Frames",
            "",
        ]
    )
    for risk_name, bucket in sorted(payload["risk_summary"].items()):
        representatives = ", ".join(bucket["representative_frames"])
        lines.append(f"- `{risk_name}`: {representatives}")

    lines.extend(
        [
            "",
            "## Frames",
            "",
            "| Name | Scene | Raw Scene | Bypass | Manifest Scene | Failure Modes |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for frame in payload["frames"]:
        manifest = frame.get("manifest") if isinstance(frame.get("manifest"), dict) else {}
        lines.append(
            f"| {frame['name']} | {frame['scene_name']} | {frame['raw_scene_name']} | {frame['bypass_flag']} | "
            f"{manifest.get('scene_tag', '-')} | {manifest.get('expected_failure_modes', '-')} |"
        )

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_float_manual_eval(cfg: FloatManualEvalConfig | None = None) -> dict[str, object]:
    config = cfg or FloatManualEvalConfig()
    model = FloatDiscreteSceneGainModel(FloatDiscreteSceneGainConfig(scene_hold_enable=config.scene_hold_enable))
    output_dir = Path(config.output_dir)
    enhanced_dir = output_dir / "enhanced"
    meta_dir = output_dir / "meta"
    enhanced_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    source_mode, items = _load_planes(config)
    resolved_manifest_csv = _resolve_manifest_csv(config)
    manifest_lookup = _load_manifest_lookup(resolved_manifest_csv)
    frames: list[dict[str, object]] = []

    for index, (name, relative_path, plane) in enumerate(items):
        result = model.process_plane_image(np.asarray(plane, dtype=np.uint8))
        enhanced = np.asarray(result.mapped_samples, dtype=np.uint8).reshape(plane.shape)
        metrics = summarize_plane(enhanced)
        manifest_row = manifest_lookup.get(relative_path) or manifest_lookup.get(Path(relative_path).name)
        frame_summary = {
            "index": index,
            "name": name,
            "relative_path": relative_path,
            "scene_name": result.scene_name,
            "raw_scene_name": result.raw_scene_name,
            "bypass_flag": result.bypass_flag,
            "stats": result.stats,
            "metrics": metrics,
            "manifest": manifest_row,
        }
        frames.append(frame_summary)

        Image.fromarray(enhanced).save(enhanced_dir / name)
        (meta_dir / f"{Path(name).stem}.json").write_text(json.dumps(frame_summary, indent=2), encoding="utf-8")

    config_payload = {
        "input_dir": str(config.input_dir),
        "output_dir": str(config.output_dir),
        "recursive": config.recursive,
        "pattern_width": config.pattern_width,
        "pattern_height": config.pattern_height,
        "scene_hold_enable": config.scene_hold_enable,
        "manifest_csv": str(resolved_manifest_csv) if resolved_manifest_csv is not None else None,
        "manifest_dir": str(config.manifest_dir),
    }
    group_summary = _build_group_summary(frames)
    risk_summary = _build_risk_summary(frames)
    report_path = output_dir / "report.md"
    payload = {
        "source_mode": source_mode,
        "input_dir": str(config.input_dir),
        "output_dir": str(output_dir),
        "frame_count": len(frames),
        "config": config_payload,
        "manifest_csv": str(resolved_manifest_csv) if resolved_manifest_csv is not None else None,
        "group_summary": group_summary,
        "risk_summary": risk_summary,
        "report_path": str(report_path),
        "frames": frames,
    }
    (output_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_markdown_report(report_path, payload)
    return payload


def main() -> dict[str, object]:
    result = run_float_manual_eval()
    print(f"Float manual eval finished: {result['frame_count']} frames from {result['source_mode']}.")
    print(f"Summary written to: {Path(result['output_dir']) / 'summary.json'}")
    return result


if __name__ == "__main__":
    main()
