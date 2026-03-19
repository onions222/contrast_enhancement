from pathlib import Path

import numpy as np
from PIL import Image

from ce_scheme3.reference_model import ContrastConfig


def test_run_temporal_sequence_returns_per_frame_metrics_and_luts():
    from ce_scheme3.temporal_runner import run_temporal_sequence

    frames = [
        np.array([[0, 16], [32, 48]], dtype=np.uint8),
        np.array([[8, 24], [40, 56]], dtype=np.uint8),
    ]

    result = run_temporal_sequence(frames, ContrastConfig(alpha_num=1, alpha_den=1))

    assert result["frame_count"] == 2
    assert len(result["frames"]) == 2
    assert "plane" in result["frames"][0]
    assert "lut" in result["frames"][0]
    assert "mean" in result["frames"][0]["metrics"]
    assert result["frames"][1]["temporal"]["lut_max_delta"] >= 0.0


def test_run_temporal_directory_reads_ordered_images(tmp_path: Path):
    from ce_scheme3.temporal_runner import run_temporal_directory

    input_dir = tmp_path / "seq"
    input_dir.mkdir()
    frame_a = np.array([[[0, 0, 0], [32, 32, 32]]], dtype=np.uint8)
    frame_b = np.array([[[16, 16, 16], [48, 48, 48]]], dtype=np.uint8)
    Image.fromarray(frame_b).save(input_dir / "frame_01.png")
    Image.fromarray(frame_a).save(input_dir / "frame_00.png")

    result = run_temporal_directory(input_dir, ContrastConfig(alpha_num=1, alpha_den=1))

    assert result["frame_count"] == 2
    assert result["frames"][0]["name"] == "frame_00.png"
    assert result["frames"][1]["name"] == "frame_01.png"


def test_export_temporal_summary_writes_json_report(tmp_path: Path):
    from ce_scheme3.temporal_runner import export_temporal_summary, run_temporal_sequence

    frames = [
        np.array([[0, 8], [16, 24]], dtype=np.uint8),
        np.array([[8, 16], [24, 32]], dtype=np.uint8),
    ]
    result = run_temporal_sequence(frames, ContrastConfig(alpha_num=1, alpha_den=1))
    output_path = tmp_path / "summary.json"

    export_temporal_summary(output_path, result)

    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8").startswith("{")


def test_run_temporal_sequence_accepts_discrete_scene_gain_model():
    from ce_scheme3.candidate_models import DiscreteSceneGainConfig, DiscreteSceneGainModel
    from ce_scheme3.temporal_runner import run_temporal_sequence

    frames = [
        np.array([[152, 160], [168, 180]], dtype=np.uint8),
        np.array([[168, 168], [168, 224]], dtype=np.uint8),
        np.array([[168, 168], [168, 224]], dtype=np.uint8),
    ]

    result = run_temporal_sequence(
        frames,
        DiscreteSceneGainConfig(),
        model_cls=DiscreteSceneGainModel,
    )

    assert result["frame_count"] == 3
    assert "scene_name" in result["frames"][0]
    assert "gain_lut" in result["frames"][0]
    assert result["frames"][1]["scene_name"] == "Normal"
    assert result["frames"][2]["scene_name"] == "Bright"
