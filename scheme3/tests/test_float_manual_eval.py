from pathlib import Path

import numpy as np
from PIL import Image


def test_run_float_manual_eval_uses_synthetic_patterns_when_input_dir_is_empty(tmp_path: Path):
    from ce_scheme3.manual_eval import FloatManualEvalConfig, run_float_manual_eval

    input_dir = tmp_path / "empty_input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"

    result = run_float_manual_eval(
        FloatManualEvalConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            recursive=True,
        )
    )

    assert result["frame_count"] > 0
    assert result["source_mode"] == "synthetic_patterns"
    assert (output_dir / "summary.json").exists()
    assert any(path.suffix == ".png" for path in (output_dir / "enhanced").iterdir())


def test_run_float_manual_eval_reads_images_and_exports_summary(tmp_path: Path):
    from ce_scheme3.manual_eval import FloatManualEvalConfig, run_float_manual_eval

    input_dir = tmp_path / "images"
    nested_dir = input_dir / "nested"
    nested_dir.mkdir(parents=True)
    bright = np.full((8, 8, 3), 220, dtype=np.uint8)
    dark = np.full((8, 8, 3), 24, dtype=np.uint8)
    Image.fromarray(bright).save(input_dir / "bright.png")
    Image.fromarray(dark).save(nested_dir / "dark.png")

    output_dir = tmp_path / "output"
    result = run_float_manual_eval(
        FloatManualEvalConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            recursive=True,
        )
    )

    assert result["frame_count"] == 2
    assert result["source_mode"] == "image_directory"
    assert (output_dir / "summary.json").exists()
    assert (output_dir / "enhanced" / "bright.png").exists()
    assert (output_dir / "enhanced" / "nested__dark.png").exists()
    summary_text = (output_dir / "summary.json").read_text(encoding="utf-8")
    assert '"scene_name"' in summary_text
    assert '"bypass_flag"' in summary_text


def test_vscode_entry_script_uses_default_zero_arg_main():
    import run_float_manual_eval

    assert callable(run_float_manual_eval.main)


def test_run_float_manual_eval_enriches_frames_from_manifest_and_reports_groups(tmp_path: Path):
    from ce_scheme3.manual_eval import FloatManualEvalConfig, run_float_manual_eval

    input_dir = tmp_path / "eval_subsets"
    dataset_dir = input_dir / "demo" / "high_key"
    dataset_dir.mkdir(parents=True)
    bright = np.full((8, 8, 3), 220, dtype=np.uint8)
    Image.fromarray(bright).save(dataset_dir / "bright.png")

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest_csv = manifest_dir / "demo_manifest.csv"
    manifest_csv.write_text(
        "\n".join(
            [
                "dataset_id,source,source_url,license,local_root,split,selected_count,scene_tag,difficulty_tag,expected_failure_modes,notes,filename,relative_path,width,height,mean_value,dark_ratio,bright_ratio,dynamic_range",
                f"demo,Demo,https://example.com,demo-license,{input_dir.as_posix()},test,1,high_key,bright_dominant,highlight_washout,manual note,bright.png,demo/high_key/bright.png,8,8,220,0.0,1.0,0.0",
            ]
        ),
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    result = run_float_manual_eval(
        FloatManualEvalConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            recursive=True,
            manifest_csv=manifest_csv,
        )
    )

    assert result["group_summary"]["high_key"]["count"] == 1
    assert result["frames"][0]["manifest"]["difficulty_tag"] == "bright_dominant"
    assert result["frames"][0]["manifest"]["expected_failure_modes"] == "highlight_washout"


def test_run_float_manual_eval_writes_markdown_report(tmp_path: Path):
    from ce_scheme3.manual_eval import FloatManualEvalConfig, run_float_manual_eval

    input_dir = tmp_path / "empty_input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"

    result = run_float_manual_eval(FloatManualEvalConfig(input_dir=input_dir, output_dir=output_dir))

    report_path = output_dir / "report.md"
    assert result["report_path"] == str(report_path)
    assert report_path.exists()
    report_text = report_path.read_text(encoding="utf-8")
    assert "# Float Manual Eval Report" in report_text
    assert "Source Mode" in report_text
    assert "Scene Summary" in report_text


def test_run_float_manual_eval_auto_selects_latest_manifest_when_not_explicitly_set(tmp_path: Path):
    from ce_scheme3.manual_eval import FloatManualEvalConfig, run_float_manual_eval

    input_dir = tmp_path / "eval_subsets"
    dataset_dir = input_dir / "demo" / "low_key"
    dataset_dir.mkdir(parents=True)
    dark = np.full((8, 8, 3), 24, dtype=np.uint8)
    Image.fromarray(dark).save(dataset_dir / "dark.png")

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    older = manifest_dir / "2026-03-16-demo_manifest.csv"
    newer = manifest_dir / "2026-03-17-demo_manifest.csv"
    older.write_text(
        "\n".join(
            [
                "dataset_id,source,source_url,license,local_root,split,selected_count,scene_tag,difficulty_tag,expected_failure_modes,notes,filename,relative_path,width,height,mean_value,dark_ratio,bright_ratio,dynamic_range",
                f"demo,Demo,https://example.com,demo-license,{input_dir.as_posix()},test,1,normal,general,general_quality_regression,older,dark.png,demo/low_key/dark.png,8,8,24,1.0,0.0,0.0",
            ]
        ),
        encoding="utf-8",
    )
    newer.write_text(
        "\n".join(
            [
                "dataset_id,source,source_url,license,local_root,split,selected_count,scene_tag,difficulty_tag,expected_failure_modes,notes,filename,relative_path,width,height,mean_value,dark_ratio,bright_ratio,dynamic_range",
                f"demo,Demo,https://example.com,demo-license,{input_dir.as_posix()},test,1,low_key,low_light,noise_boost|shadow_crush,newer,dark.png,demo/low_key/dark.png,8,8,24,1.0,0.0,0.0",
            ]
        ),
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    result = run_float_manual_eval(
        FloatManualEvalConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            recursive=True,
            manifest_dir=manifest_dir,
        )
    )

    assert result["manifest_csv"] == str(newer)
    assert result["frames"][0]["manifest"]["notes"] == "newer"


def test_run_float_manual_eval_prefers_public_first_batch_manifest_over_raw_manifests(tmp_path: Path):
    from ce_scheme3.manual_eval import FloatManualEvalConfig, run_float_manual_eval

    input_dir = tmp_path / "eval_subsets"
    dataset_dir = input_dir / "demo" / "normal"
    dataset_dir.mkdir(parents=True)
    Image.fromarray(np.full((8, 8, 3), 120, dtype=np.uint8)).save(dataset_dir / "sample.png")

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    raw_manifest = manifest_dir / "2026-03-17-wikimedia_commons_manifest.csv"
    public_manifest = manifest_dir / "2026-03-17-public_first_batch_manifest.csv"
    raw_manifest.write_text(
        "\n".join(
            [
                "dataset_id,source,source_url,license,local_root,split,selected_count,scene_tag,difficulty_tag,expected_failure_modes,notes,filename,relative_path,width,height,mean_value,dark_ratio,bright_ratio,dynamic_range",
                f"demo,Demo,https://example.com,demo-license,{input_dir.as_posix()},test,1,normal,general,general_quality_regression,raw,sample.png,demo/normal/sample.png,8,8,120,0.0,0.0,0.0",
            ]
        ),
        encoding="utf-8",
    )
    public_manifest.write_text(
        "\n".join(
            [
                "dataset_id,source,source_url,license,local_root,split,selected_count,scene_tag,difficulty_tag,expected_failure_modes,notes,filename,relative_path,width,height,mean_value,dark_ratio,bright_ratio,dynamic_range",
                f"demo,Demo,https://example.com,demo-license,{input_dir.as_posix()},test,1,normal,general,general_quality_regression,public,sample.png,demo/normal/sample.png,8,8,120,0.0,0.0,0.0",
            ]
        ),
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    result = run_float_manual_eval(
        FloatManualEvalConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            recursive=True,
            manifest_dir=manifest_dir,
        )
    )

    assert result["manifest_csv"] == str(public_manifest)
    assert result["frames"][0]["manifest"]["notes"] == "public"


def test_markdown_report_includes_risk_summary_and_representative_images(tmp_path: Path):
    from ce_scheme3.manual_eval import FloatManualEvalConfig, run_float_manual_eval

    input_dir = tmp_path / "eval_subsets"
    high_dir = input_dir / "demo" / "high_key"
    low_dir = input_dir / "demo" / "low_key"
    high_dir.mkdir(parents=True)
    low_dir.mkdir(parents=True)
    Image.fromarray(np.full((8, 8, 3), 220, dtype=np.uint8)).save(high_dir / "bright.png")
    Image.fromarray(np.full((8, 8, 3), 24, dtype=np.uint8)).save(low_dir / "dark.png")

    manifest_csv = tmp_path / "demo_manifest.csv"
    manifest_csv.write_text(
        "\n".join(
            [
                "dataset_id,source,source_url,license,local_root,split,selected_count,scene_tag,difficulty_tag,expected_failure_modes,notes,filename,relative_path,width,height,mean_value,dark_ratio,bright_ratio,dynamic_range",
                f"demo,Demo,https://example.com,demo-license,{input_dir.as_posix()},test,1,high_key,bright_dominant,highlight_washout,bright-note,bright.png,demo/high_key/bright.png,8,8,220,0.0,1.0,0.0",
                f"demo,Demo,https://example.com,demo-license,{input_dir.as_posix()},test,1,low_key,low_light,noise_boost|shadow_crush,dark-note,dark.png,demo/low_key/dark.png,8,8,24,1.0,0.0,0.0",
            ]
        ),
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    result = run_float_manual_eval(
        FloatManualEvalConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            manifest_csv=manifest_csv,
        )
    )

    report_text = Path(result["report_path"]).read_text(encoding="utf-8")
    assert "Risk Summary" in report_text
    assert "highlight_washout" in report_text
    assert "noise_boost" in report_text
    assert "Representative Frames" in report_text
    assert "bright.png" in report_text
    assert "dark.png" in report_text
