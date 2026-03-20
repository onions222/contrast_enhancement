from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image


def _write_manifest(path: Path, input_dir: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "dataset_id,source,source_url,license,local_root,split,selected_count,scene_tag,difficulty_tag,expected_failure_modes,notes,filename,relative_path,width,height,mean_value,dark_ratio,bright_ratio,dynamic_range",
                f"demo,Demo,https://example.com,demo-license,{input_dir.as_posix()},test,1,high_key,bright_dominant,highlight_washout|over_enhancement,bright sample,bright.png,demo/high_key/bright.png,12,12,235,0.0,1.0,0.0",
                f"demo,Demo,https://example.com,demo-license,{input_dir.as_posix()},test,1,faces_skin,skin_proxy,color_shift|skin_tone_shift,skin sample,skin.png,demo/faces_skin/skin.png,12,12,151,0.0,0.0,24.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_run_float_full_eval_writes_compare_views_tables_and_report(tmp_path: Path):
    from ce_scheme3.full_eval import FloatFullEvalConfig, run_float_full_eval

    input_dir = tmp_path / "eval_subsets"
    high_dir = input_dir / "demo" / "high_key"
    skin_dir = input_dir / "demo" / "faces_skin"
    high_dir.mkdir(parents=True)
    skin_dir.mkdir(parents=True)

    Image.fromarray(np.full((12, 12, 3), 235, dtype=np.uint8)).save(high_dir / "bright.png")
    Image.fromarray(np.full((12, 12, 3), [170, 132, 116], dtype=np.uint8)).save(skin_dir / "skin.png")

    manifest_csv = tmp_path / "demo_manifest.csv"
    _write_manifest(manifest_csv, input_dir)

    output_dir = tmp_path / "output"
    result = run_float_full_eval(
        FloatFullEvalConfig(
            dataset_roots=(input_dir,),
            output_dir=output_dir,
            manifest_csv=manifest_csv,
        )
    )

    assert result["frame_count"] == 2
    assert (output_dir / "comparisons" / "demo" / "high_key" / "demo__high_key__bright_compare.png").exists()
    assert (output_dir / "comparisons" / "demo" / "faces_skin" / "demo__faces_skin__skin_compare.png").exists()
    assert (output_dir / "tables" / "per_image_metrics.csv").exists()
    assert (output_dir / "tables" / "risk_samples.csv").exists()
    assert (output_dir / "reports" / "report.md").exists()
    assert (output_dir / "reports" / "summary.json").exists()

    report_text = (output_dir / "reports" / "report.md").read_text(encoding="utf-8")
    assert "高风险样本" in report_text
    assert "各子数据集结果分析" in report_text
    assert "指标体系" in report_text


def test_run_float_full_eval_exports_metrics_and_high_risk_sample_details(tmp_path: Path):
    from ce_scheme3.full_eval import FloatFullEvalConfig, run_float_full_eval

    input_dir = tmp_path / "eval_subsets"
    high_dir = input_dir / "demo" / "high_key"
    text_dir = input_dir / "demo" / "text_ui"
    high_dir.mkdir(parents=True)
    text_dir.mkdir(parents=True)

    bright = np.full((24, 24, 3), [228, 226, 224], dtype=np.uint8)
    bright[4:20, 10:18] = [252, 252, 250]
    bright[4:20, 8:10] = [168, 166, 162]

    text = np.full((24, 24, 3), [12, 10, 18], dtype=np.uint8)
    text[8:16, 5:19] = [228, 72, 190]
    text[9:15, 7:17] = [248, 214, 236]
    Image.fromarray(bright).save(high_dir / "bright.png")
    Image.fromarray(text).save(text_dir / "text.png")

    manifest_csv = tmp_path / "demo_manifest.csv"
    manifest_csv.write_text(
        "\n".join(
            [
                "dataset_id,source,source_url,license,local_root,split,selected_count,scene_tag,difficulty_tag,expected_failure_modes,notes,filename,relative_path,width,height,mean_value,dark_ratio,bright_ratio,dynamic_range",
                f"demo,Demo,https://example.com,demo-license,{input_dir.as_posix()},test,1,high_key,bright_dominant,highlight_washout|over_enhancement,bright sample,bright.png,demo/high_key/bright.png,24,24,228,0.0,0.8,24.0",
                f"demo,Demo,https://example.com,demo-license,{input_dir.as_posix()},test,1,text_ui,text_ui|low_light,color_shift|shadow_crush,text sample,text.png,demo/text_ui/text.png,24,24,42,0.8,0.0,236.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    run_float_full_eval(
        FloatFullEvalConfig(
            dataset_roots=(input_dir,),
            output_dir=output_dir,
            manifest_csv=manifest_csv,
        )
    )

    metrics_rows = list(csv.DictReader((output_dir / "tables" / "per_image_metrics.csv").open(encoding="utf-8")))
    assert len(metrics_rows) == 2
    assert {"risk_score", "highlight_clip_ratio_delta", "channel_ratio_drift", "scene_name", "bypass_flag"} <= set(
        metrics_rows[0].keys()
    )

    risk_rows = list(csv.DictReader((output_dir / "tables" / "risk_samples.csv").open(encoding="utf-8")))
    assert risk_rows
    assert {"risk_types", "triggered_metrics", "relative_path", "compare_path"} <= set(risk_rows[0].keys())

    per_image_json = json.loads(
        (output_dir / "meta" / "per_image" / "demo__high_key__bright.json").read_text(encoding="utf-8")
    )
    assert {"metrics", "risk_types", "triggered_metrics", "compare_path", "manifest"} <= set(per_image_json.keys())
    assert "highlight_clip_ratio_delta" in per_image_json["metrics"]

    summary = json.loads((output_dir / "reports" / "summary.json").read_text(encoding="utf-8"))
    assert summary["high_risk_samples"]
    assert "subdataset_summary" in summary
