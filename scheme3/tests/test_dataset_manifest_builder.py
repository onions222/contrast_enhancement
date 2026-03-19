from pathlib import Path

import numpy as np
from PIL import Image


def test_build_manifest_entries_classifies_basic_scene_buckets(tmp_path: Path):
    from ce_scheme3.dataset_manifest_builder import build_manifest_entries

    raw_root = tmp_path / "raw" / "demo"
    raw_root.mkdir(parents=True)
    Image.fromarray(np.full((8, 8, 3), 220, dtype=np.uint8)).save(raw_root / "bright.png")
    Image.fromarray(np.full((8, 8, 3), 24, dtype=np.uint8)).save(raw_root / "dark.png")
    normal = np.zeros((8, 8, 3), dtype=np.uint8)
    normal[:, :4] = 96
    normal[:, 4:] = 160
    Image.fromarray(normal).save(raw_root / "normal.png")

    entries = build_manifest_entries(
        dataset_id="demo",
        source="Demo Source",
        source_url="https://example.com/demo",
        license_name="demo-license",
        input_root=raw_root,
        split="test",
    )

    by_name = {entry.filename: entry for entry in entries}
    assert len(entries) == 3
    assert by_name["bright.png"].scene_tag == "high_key"
    assert "highlight_washout" in by_name["bright.png"].expected_failure_modes
    assert by_name["dark.png"].scene_tag == "low_key"
    assert "noise_boost" in by_name["dark.png"].expected_failure_modes
    assert by_name["normal.png"].scene_tag == "normal"
    assert by_name["normal.png"].selected_count == 1


def test_export_manifest_writes_csv_and_copies_eval_subset(tmp_path: Path):
    from ce_scheme3.dataset_manifest_builder import (
        build_manifest_entries,
        export_manifest_csv,
        export_selected_subset,
    )

    raw_root = tmp_path / "raw" / "demo"
    raw_root.mkdir(parents=True)
    low_key = np.full((8, 8, 3), 24, dtype=np.uint8)
    Image.fromarray(low_key).save(raw_root / "dark.png")

    entries = build_manifest_entries(
        dataset_id="demo",
        source="Demo Source",
        source_url="https://example.com/demo",
        license_name="demo-license",
        input_root=raw_root,
        split="test",
    )

    manifest_path = tmp_path / "derived" / "manifests" / "demo_manifest.csv"
    export_manifest_csv(manifest_path, entries)
    subset_root = tmp_path / "derived" / "eval_subsets"
    copied_files = export_selected_subset(entries, subset_root)

    assert manifest_path.exists()
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert "dataset_id,source,source_url,license,local_root,split,selected_count,scene_tag" in manifest_text
    assert "dark.png" in manifest_text
    assert len(copied_files) == 1
    assert copied_files[0].exists()
    assert copied_files[0].parts[-3:] == ("demo", "low_key", "dark.png")


def test_build_arg_parser_accepts_manifest_generation_options():
    from ce_scheme3.dataset_manifest_builder import build_arg_parser

    parser = build_arg_parser()
    args = parser.parse_args(
        [
            "input_dir",
            "output_csv",
            "--dataset-id",
            "exdark",
            "--source",
            "ExDark",
            "--source-url",
            "https://example.com/exdark",
            "--license",
            "bsd",
            "--copy-subset-to",
            "subset_dir",
        ]
    )

    assert args.input_root == "input_dir"
    assert args.output_csv == "output_csv"
    assert args.dataset_id == "exdark"
    assert args.copy_subset_to == "subset_dir"
