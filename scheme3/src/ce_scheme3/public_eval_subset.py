from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from ce_scheme3.dataset_manifest_builder import ManifestEntry, build_manifest_entries, export_manifest_csv


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_ROOT = REPO_ROOT / "data" / "raw"
DEFAULT_MANIFEST_DIR = REPO_ROOT / "data" / "derived" / "manifests"
DEFAULT_EVAL_SUBSET_ROOT = REPO_ROOT / "data" / "derived" / "eval_subsets"
WIKIMEDIA_CURATED_METADATA = "2026-03-17-wikimedia_commons_curated.json"


@dataclass(frozen=True)
class PublicSourceSpec:
    dataset_id: str
    source: str
    source_url: str
    license_name: str
    relative_root: str


@dataclass(frozen=True)
class PublicEvalSubsetConfig:
    raw_root: Path = DEFAULT_RAW_ROOT
    manifest_dir: Path = DEFAULT_MANIFEST_DIR
    eval_subset_root: Path = DEFAULT_EVAL_SUBSET_ROOT
    subset_name: str = "public_first_batch"
    split: str = "test"


DEFAULT_PUBLIC_SOURCE_SPECS = (
    PublicSourceSpec(
        dataset_id="wikimedia_commons",
        source="Wikimedia Commons Curated Set",
        source_url="https://commons.wikimedia.org/",
        license_name="see-per-file-license-on-source-page",
        relative_root="wikimedia_commons",
    ),
    PublicSourceSpec(
        dataset_id="mit_adobe_fivek",
        source="MIT-Adobe FiveK",
        source_url="https://data.csail.mit.edu/graphics/fivek/",
        license_name="research-license-on-source-site",
        relative_root="mit_adobe_fivek",
    ),
    PublicSourceSpec(
        dataset_id="bsds500",
        source="BSDS500",
        source_url="https://www2.eecs.berkeley.edu/Research/Projects/CS/vision/grouping/resources.html",
        license_name="benchmark-terms-on-source-site",
        relative_root="bsds500",
    ),
    PublicSourceSpec(
        dataset_id="exdark",
        source="ExDark",
        source_url="https://github.com/cs-chan/Exclusively-Dark-Image-Dataset",
        license_name="BSD-3-Clause-plus-dataset-terms",
        relative_root="exdark",
    ),
    PublicSourceSpec(
        dataset_id="sid",
        source="SID",
        source_url="https://cchen156.github.io/SID.html",
        license_name="dataset-terms-on-source-site",
        relative_root="sid",
    ),
    PublicSourceSpec(
        dataset_id="text_in_the_dark",
        source="Text in the Dark",
        source_url="https://github.com/chunchet-ng/Text-in-the-Dark",
        license_name="dataset-terms-on-source-site",
        relative_root="text_in_the_dark",
    ),
    PublicSourceSpec(
        dataset_id="usc_sipi",
        source="USC-SIPI",
        source_url="https://sipi.usc.edu/database/",
        license_name="research-use-check-each-file",
        relative_root="usc_sipi",
    ),
)


BUCKET_TARGETS = {
    "high_key": 8,
    "normal": 8,
    "low_key": 12,
    "low_light_noisy": 8,
    "faces_skin": 6,
    "text_ui": 6,
    "gradient": 4,
    "high_contrast": 4,
}
BUCKET_SELECTION_ORDER = (
    "faces_skin",
    "text_ui",
    "gradient",
    "low_light_noisy",
    "high_key",
    "low_key",
    "normal",
    "high_contrast",
)

FACE_KEYWORDS = ("face", "portrait", "person", "people", "man", "woman", "child", "girl", "boy", "skin")
TEXT_KEYWORDS = ("text", "sign", "subtitle", "menu", "screen", "board", "poster", "ui")
GRADIENT_KEYWORDS = ("sky", "wall", "gradient", "ramp", "smooth")


def _keyword_score(entry: ManifestEntry, keywords: tuple[str, ...]) -> int:
    haystack = f"{entry.filename} {entry.relative_path}".lower()
    tokens = set(re.findall(r"[a-z0-9]+", haystack))
    return sum(1 for keyword in keywords if keyword in tokens)


def _is_high_key_candidate(entry: ManifestEntry) -> bool:
    return entry.dataset_id in {"wikimedia_commons", "mit_adobe_fivek", "bsds500"} and entry.scene_tag == "high_key"


def _is_normal_candidate(entry: ManifestEntry) -> bool:
    return entry.dataset_id in {"wikimedia_commons", "mit_adobe_fivek", "bsds500"} and entry.scene_tag == "normal"


def _is_low_key_candidate(entry: ManifestEntry) -> bool:
    return entry.dataset_id in {"wikimedia_commons", "exdark", "sid"} and entry.scene_tag == "low_key"


def _is_low_light_noisy_candidate(entry: ManifestEntry) -> bool:
    return entry.dataset_id in {"wikimedia_commons", "exdark", "sid"} and (
        entry.scene_tag == "low_light_noisy" or (entry.scene_tag == "low_key" and entry.dark_ratio >= 0.70)
    )


def _is_faces_skin_candidate(entry: ManifestEntry) -> bool:
    return entry.dataset_id in {"wikimedia_commons", "mit_adobe_fivek"} and (
        entry.scene_tag == "faces_skin" or _keyword_score(entry, FACE_KEYWORDS) > 0
    )


def _is_text_ui_candidate(entry: ManifestEntry) -> bool:
    return entry.dataset_id in {"wikimedia_commons", "text_in_the_dark", "exdark"} and _keyword_score(entry, TEXT_KEYWORDS) > 0


def _is_gradient_candidate(entry: ManifestEntry) -> bool:
    return entry.dataset_id in {"wikimedia_commons", "usc_sipi", "bsds500", "mit_adobe_fivek"} and (
        _keyword_score(entry, GRADIENT_KEYWORDS) > 0 or entry.dynamic_range <= 64.0
    )


def _is_high_contrast_candidate(entry: ManifestEntry) -> bool:
    return entry.dataset_id in {"wikimedia_commons", "bsds500", "mit_adobe_fivek"} and entry.dynamic_range >= 160.0


def _bucket_candidates(entries: list[ManifestEntry], bucket_name: str) -> list[ManifestEntry]:
    predicates = {
        "high_key": _is_high_key_candidate,
        "normal": _is_normal_candidate,
        "low_key": _is_low_key_candidate,
        "low_light_noisy": _is_low_light_noisy_candidate,
        "faces_skin": _is_faces_skin_candidate,
        "text_ui": _is_text_ui_candidate,
        "gradient": _is_gradient_candidate,
        "high_contrast": _is_high_contrast_candidate,
    }
    predicate = predicates[bucket_name]
    return [entry for entry in entries if predicate(entry)]


def _sort_key(bucket_name: str, entry: ManifestEntry) -> tuple[float, ...]:
    if bucket_name == "high_key":
        return (-entry.mean_luma, entry.dark_ratio, -entry.bright_ratio)
    if bucket_name == "normal":
        return (abs(entry.mean_luma - 128.0), abs(entry.dynamic_range - 128.0))
    if bucket_name == "low_key":
        return (entry.mean_luma, -entry.dark_ratio, -entry.dynamic_range)
    if bucket_name == "low_light_noisy":
        return (entry.mean_luma, -entry.dark_ratio, -entry.dynamic_range)
    if bucket_name == "faces_skin":
        return (-_keyword_score(entry, FACE_KEYWORDS), abs(entry.mean_luma - 144.0))
    if bucket_name == "text_ui":
        return (-_keyword_score(entry, TEXT_KEYWORDS), abs(entry.mean_luma - 128.0))
    if bucket_name == "gradient":
        return (-_keyword_score(entry, GRADIENT_KEYWORDS), abs(entry.dynamic_range - 48.0), abs(entry.mean_luma - 160.0))
    return (-entry.dynamic_range, -entry.bright_ratio, entry.dark_ratio)


def _select_entries_by_bucket(entries: list[ManifestEntry]) -> dict[str, list[ManifestEntry]]:
    selected_keys: set[tuple[str, str]] = set()
    selected: dict[str, list[ManifestEntry]] = {bucket_name: [] for bucket_name in BUCKET_TARGETS}
    for bucket_name in BUCKET_SELECTION_ORDER:
        target_count = BUCKET_TARGETS[bucket_name]
        bucket_entries = sorted(_bucket_candidates(entries, bucket_name), key=lambda entry: _sort_key(bucket_name, entry))
        picked: list[ManifestEntry] = []
        for entry in bucket_entries:
            entry_key = (entry.dataset_id, entry.relative_path)
            if entry_key in selected_keys:
                continue
            picked.append(entry)
            selected_keys.add(entry_key)
            if len(picked) >= target_count:
                break
        selected[bucket_name] = picked
    return selected


def _load_wikimedia_override_map(raw_root: Path) -> dict[str, dict[str, object]]:
    metadata_path = Path(raw_root) / "wikimedia_commons" / WIKIMEDIA_CURATED_METADATA
    if not metadata_path.exists():
        return {}
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    downloaded = payload.get("downloaded", []) if isinstance(payload, dict) else []
    override_map: dict[str, dict[str, object]] = {}
    for item in downloaded:
        filename = str(item.get("filename", "")).strip()
        if not filename:
            continue
        override_map[filename] = item
    return override_map


def _apply_source_overrides(
    entries: list[ManifestEntry],
    *,
    dataset_id: str,
    raw_root: Path,
) -> list[ManifestEntry]:
    if dataset_id != "wikimedia_commons":
        return entries
    override_map = _load_wikimedia_override_map(raw_root)
    if not override_map:
        return entries

    output: list[ManifestEntry] = []
    for entry in entries:
        override = override_map.get(entry.filename)
        if override is None:
            continue
        failure_modes = override.get("expected_failure_modes", [])
        notes = str(override.get("notes", entry.notes))
        expected_bucket = str(override.get("expected_bucket", entry.scene_tag))
        output.append(
            replace(
                entry,
                scene_tag=expected_bucket,
                expected_failure_modes="|".join(str(mode) for mode in failure_modes) if failure_modes else entry.expected_failure_modes,
                notes=notes,
            )
        )
    return output


def _copy_selected_subset(
    selected: dict[str, list[ManifestEntry]],
    eval_subset_root: Path,
    subset_name: str,
) -> list[ManifestEntry]:
    subset_root = eval_subset_root / subset_name
    if subset_root.exists():
        shutil.rmtree(subset_root)
    output_entries: list[ManifestEntry] = []
    for bucket_name, entries in selected.items():
        for entry in entries:
            source_path = Path(entry.local_root) / entry.relative_path
            destination_filename = f"{entry.dataset_id}__{entry.filename}"
            relative_path = Path(subset_name) / bucket_name / destination_filename
            destination = eval_subset_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination)
            output_entries.append(
                replace(
                    entry,
                    local_root=str(eval_subset_root),
                    scene_tag=bucket_name,
                    difficulty_tag=f"{entry.difficulty_tag}|original_scene_{entry.scene_tag}",
                    notes=f"{entry.notes} | selected_for={bucket_name}",
                    filename=destination_filename,
                    relative_path=relative_path.as_posix(),
                )
            )
    return output_entries


def build_public_eval_subset(
    config: PublicEvalSubsetConfig | None = None,
    *,
    source_specs: tuple[PublicSourceSpec, ...] = DEFAULT_PUBLIC_SOURCE_SPECS,
) -> dict[str, object]:
    cfg = config or PublicEvalSubsetConfig()
    all_entries: list[ManifestEntry] = []
    available_sources: list[str] = []
    missing_sources: list[str] = []

    for source_spec in source_specs:
        input_root = cfg.raw_root / source_spec.relative_root
        if not input_root.exists():
            missing_sources.append(source_spec.dataset_id)
            continue
        entries = build_manifest_entries(
            dataset_id=source_spec.dataset_id,
            source=source_spec.source,
            source_url=source_spec.source_url,
            license_name=source_spec.license_name,
            input_root=input_root,
            split=cfg.split,
        )
        entries = _apply_source_overrides(entries, dataset_id=source_spec.dataset_id, raw_root=cfg.raw_root)
        if entries:
            available_sources.append(source_spec.dataset_id)
            all_entries.extend(entries)
        else:
            missing_sources.append(source_spec.dataset_id)

    master_manifest_path = cfg.manifest_dir / "2026-03-17-public_sources_master_manifest.csv"
    selected_manifest_path = cfg.manifest_dir / "2026-03-17-public_first_batch_manifest.csv"
    summary_path = cfg.manifest_dir / "2026-03-17-public_first_batch_summary.json"
    export_manifest_csv(master_manifest_path, all_entries)

    selected = _select_entries_by_bucket(all_entries)
    selected_entries = _copy_selected_subset(selected, cfg.eval_subset_root, cfg.subset_name)
    export_manifest_csv(selected_manifest_path, selected_entries)

    bucket_summary = {
        bucket_name: {
            "target_count": BUCKET_TARGETS[bucket_name],
            "selected_count": len(entries),
            "selected_files": [entry.filename for entry in entries],
            "shortage": max(BUCKET_TARGETS[bucket_name] - len(entries), 0),
        }
        for bucket_name, entries in selected.items()
    }
    summary = {
        "raw_root": str(cfg.raw_root),
        "manifest_dir": str(cfg.manifest_dir),
        "eval_subset_root": str(cfg.eval_subset_root),
        "subset_name": cfg.subset_name,
        "available_sources": available_sources,
        "missing_sources": missing_sources,
        "master_manifest_path": str(master_manifest_path),
        "selected_manifest_path": str(selected_manifest_path),
        "summary_path": str(summary_path),
        "master_entry_count": len(all_entries),
        "selected_entry_count": len(selected_entries),
        "bucket_summary": bucket_summary,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> dict[str, object]:
    summary = build_public_eval_subset()
    print(f"Public eval subset ready: {summary['selected_entry_count']} files selected.")
    print(f"Selected manifest: {summary['selected_manifest_path']}")
    if summary["missing_sources"]:
        print(f"Missing sources: {', '.join(summary['missing_sources'])}")
    return summary


if __name__ == "__main__":
    main()
