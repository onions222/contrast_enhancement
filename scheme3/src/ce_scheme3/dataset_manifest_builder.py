from __future__ import annotations

import argparse
import csv
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ce_scheme3.image_io import rgb_to_luma
from ce_scheme3.metrics import summarize_plane

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


@dataclass(frozen=True)
class ManifestEntry:
    dataset_id: str
    source: str
    source_url: str
    license: str
    local_root: str
    split: str
    selected_count: int
    scene_tag: str
    difficulty_tag: str
    expected_failure_modes: str
    notes: str
    filename: str
    relative_path: str
    width: int
    height: int
    mean_luma: float
    dark_ratio: float
    bright_ratio: float
    dynamic_range: float


def _iter_image_paths(input_root: Path) -> list[Path]:
    return sorted(path for path in input_root.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS)


def _load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def _infer_scene_tag(summary: dict[str, float]) -> str:
    if summary["mean"] >= 200.0:
        return "high_key"
    if summary["mean"] >= 176.0 and summary["bright_ratio"] >= 0.10:
        return "high_key"
    if summary["mean"] <= 96.0 and summary["dark_ratio"] >= 0.55:
        return "low_key"
    return "normal"


def _infer_difficulty_tags(summary: dict[str, float], scene_tag: str) -> list[str]:
    tags: list[str] = []
    if scene_tag == "high_key":
        tags.append("bright_dominant")
    if scene_tag == "low_key":
        tags.append("low_light")
    if summary["dynamic_range"] <= 32.0:
        tags.append("low_dynamic_range")
    if summary["dynamic_range"] >= 192.0:
        tags.append("high_dynamic_range")
    if summary["std"] <= 12.0:
        tags.append("smooth_gradient")
    return tags or ["general"]


def _infer_failure_modes(scene_tag: str, difficulty_tags: list[str]) -> list[str]:
    failure_modes: list[str] = []
    if scene_tag == "high_key":
        failure_modes.extend(["highlight_washout", "over_enhancement"])
    if scene_tag == "low_key":
        failure_modes.extend(["noise_boost", "shadow_crush"])
    if "low_dynamic_range" in difficulty_tags:
        failure_modes.append("bypass_miss")
    if "smooth_gradient" in difficulty_tags:
        failure_modes.append("banding")
    if "high_dynamic_range" in difficulty_tags:
        failure_modes.append("halo")
    return failure_modes or ["general_quality_regression"]


def build_manifest_entries(
    *,
    dataset_id: str,
    source: str,
    source_url: str,
    license_name: str,
    input_root: Path,
    split: str = "test",
) -> list[ManifestEntry]:
    root = Path(input_root)
    entries: list[ManifestEntry] = []
    for image_path in _iter_image_paths(root):
        rgb = _load_rgb(image_path)
        plane = rgb_to_luma(rgb)
        summary = summarize_plane(plane)
        scene_tag = _infer_scene_tag(summary)
        difficulty_tags = _infer_difficulty_tags(summary, scene_tag)
        failure_modes = _infer_failure_modes(scene_tag, difficulty_tags)
        relative_path = image_path.relative_to(root).as_posix()
        entries.append(
            ManifestEntry(
                dataset_id=dataset_id,
                source=source,
                source_url=source_url,
                license=license_name,
                local_root=root.as_posix(),
                split=split,
                selected_count=1,
                scene_tag=scene_tag,
                difficulty_tag="|".join(difficulty_tags),
                expected_failure_modes="|".join(failure_modes),
                notes="auto-generated manifest entry",
                filename=image_path.name,
                relative_path=relative_path,
                width=int(rgb.shape[1]),
                height=int(rgb.shape[0]),
                mean_luma=float(summary["mean"]),
                dark_ratio=float(summary["dark_ratio"]),
                bright_ratio=float(summary["bright_ratio"]),
                dynamic_range=float(summary["dynamic_range"]),
            )
        )
    return entries


def export_manifest_csv(output_csv: Path, entries: list[ManifestEntry]) -> None:
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(ManifestEntry.__dataclass_fields__.keys())
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            writer.writerow(asdict(entry))


def export_selected_subset(entries: list[ManifestEntry], subset_root: Path) -> list[Path]:
    output_root = Path(subset_root)
    copied_paths: list[Path] = []
    for entry in entries:
        source_path = Path(entry.local_root) / entry.relative_path
        destination = output_root / entry.dataset_id / entry.scene_tag / entry.filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        copied_paths.append(destination)
    return copied_paths


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a manifest and organized eval subset for contrast test images.")
    parser.add_argument("input_root")
    parser.add_argument("output_csv")
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--license", required=True, dest="license_name")
    parser.add_argument("--split", default="test")
    parser.add_argument("--copy-subset-to")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    entries = build_manifest_entries(
        dataset_id=args.dataset_id,
        source=args.source,
        source_url=args.source_url,
        license_name=args.license_name,
        input_root=Path(args.input_root),
        split=args.split,
    )
    export_manifest_csv(Path(args.output_csv), entries)
    if args.copy_subset_to:
        export_selected_subset(entries, Path(args.copy_subset_to))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
