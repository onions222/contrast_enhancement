from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ce_scheme1.image_io import rgb_to_luma
from ce_scheme1.metrics import summarize_plane, summarize_temporal_change
from ce_scheme1.reference_model import ContrastConfig, ContrastReferenceModel

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}


def _apply_lut_to_plane(plane: np.ndarray, lut: list[int]) -> np.ndarray:
    """把 8bit LUT 直接查表应用到灰度平面。"""
    lut_array = np.asarray(lut, dtype=np.uint8)
    return lut_array[np.asarray(plane, dtype=np.uint8)]


def run_temporal_sequence(
    frames: list[np.ndarray],
    cfg: ContrastConfig,
    *,
    model_cls: type[Any] = ContrastReferenceModel,
) -> dict[str, object]:
    """按时间顺序处理一组帧，并记录每帧增强结果及时域指标。

    该函数会复用同一个模型实例，因此能够保留 LUT 时域状态，适合验证视频序列
    下的稳定性、闪烁和场景切换行为。
    """
    model = model_cls(cfg)
    results: list[dict[str, object]] = []
    prev_plane: np.ndarray | None = None
    prev_lut: list[int] | None = None

    for index, frame in enumerate(frames):
        plane = np.asarray(frame, dtype=np.uint8)
        if hasattr(model, "process_plane_image"):
            frame_result = model.process_plane_image(plane)
        else:
            frame_result = model.process_frame(plane.reshape(-1).tolist())
        enhanced_plane = np.asarray(frame_result.mapped_samples, dtype=np.uint8).reshape(plane.shape)
        metrics = summarize_plane(enhanced_plane)
        temporal = (
            summarize_temporal_change(prev_plane, enhanced_plane, prev_lut, frame_result.lut)
            if prev_plane is not None and prev_lut is not None
            else {
                "frame_mean_abs_delta": 0.0,
                "frame_max_abs_delta": 0.0,
                "lut_mean_abs_delta": 0.0,
                "lut_max_delta": 0.0,
            }
        )
        frame_payload: dict[str, object] = {
            "index": index,
            "name": f"frame_{index:04d}",
            "plane": plane,
            "enhanced_plane": enhanced_plane,
            "histogram": frame_result.histogram,
            "lut": frame_result.lut,
            "metrics": metrics,
            "temporal": temporal,
        }
        for attr in ("gain_lut", "scene_id", "scene_name", "raw_scene_id", "raw_scene_name", "bypass_flag", "stats"):
            if hasattr(frame_result, attr):
                frame_payload[attr] = getattr(frame_result, attr)
        results.append(frame_payload)
        prev_plane = enhanced_plane
        prev_lut = frame_result.lut

    return {"frame_count": len(results), "frames": results}


def run_temporal_directory(
    input_dir: Path,
    cfg: ContrastConfig,
    *,
    model_cls: type[Any] = ContrastReferenceModel,
) -> dict[str, object]:
    """读取目录中的图像序列，转为 luma 后执行时域评估。"""
    frames: list[np.ndarray] = []
    names: list[str] = []
    for image_path in sorted(Path(input_dir).iterdir()):
        if image_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        rgb = np.asarray(Image.open(image_path).convert("RGB"), dtype=np.uint8)
        frames.append(rgb_to_luma(rgb))
        names.append(image_path.name)

    result = run_temporal_sequence(frames, cfg, model_cls=model_cls)
    for frame_entry, name in zip(result["frames"], names):
        frame_entry["name"] = name
    return result


def export_temporal_summary(output_path: Path, result: dict[str, object]) -> None:
    """把时域评估结果导出为精简 JSON，便于离线比对和归档。"""
    serializable_frames = []
    for frame in result["frames"]:
        serializable_frames.append(
            {
                "index": frame["index"],
                "name": frame["name"],
                "histogram": frame["histogram"],
                "lut": frame["lut"],
                "metrics": frame["metrics"],
                "temporal": frame["temporal"],
            }
        )
    payload = {"frame_count": result["frame_count"], "frames": serializable_frames}
    Path(output_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
