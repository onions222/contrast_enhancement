import numpy as np
from dataclasses import dataclass

from ce_scheme3.reference_model import ContrastConfig, ContrastReferenceModel


def rgb_to_value(rgb: np.ndarray) -> np.ndarray:
    """把 RGB 图像转换成 HSV 的 8bit V 平面。"""
    rgb_u8 = np.asarray(rgb, dtype=np.uint8)
    return np.max(rgb_u8, axis=2).astype(np.uint8)


def apply_value_lut_to_rgb(rgb: np.ndarray, lut: list[int]) -> np.ndarray:
    """依据 V-domain LUT 推导逐像素 gain，并作用到 RGB 三通道。

    先计算输入 value，再查表得到目标 value，随后用 `v_out / v_in` 形成 gain。
    当输入 value 为 0 时用 1 做分母保护，最终结果裁剪到 8bit RGB 范围。
    """
    value_in = rgb_to_value(rgb)
    lut_array = np.asarray(lut, dtype=np.uint16)
    value_out = lut_array[value_in]
    gain = value_out.astype(np.float32) / np.maximum(value_in, 1).astype(np.float32)
    rgb_out = np.clip(rgb.astype(np.float32) * gain[..., None], 0, 255)
    return rgb_out.astype(np.uint8)


@dataclass(frozen=True)
class ImageProcessResult:
    enhanced_rgb: np.ndarray
    lut: list[int]
    stats: dict[str, float | int]


def process_rgb_image(rgb: np.ndarray, cfg: ContrastConfig) -> ImageProcessResult:
    """对单张 RGB 图像运行参考模型，并返回增强结果与摘要统计。"""
    model = ContrastReferenceModel(cfg)
    value_in = rgb_to_value(rgb)
    frame_result = model.process_frame(value_in.reshape(-1).tolist())
    enhanced_rgb = apply_value_lut_to_rgb(rgb, frame_result.lut)
    value_out = rgb_to_value(enhanced_rgb)
    stats: dict[str, float | int] = {
        "mean_value_in": float(np.mean(value_in)),
        "mean_value_out": float(np.mean(value_out)),
        "min_value_in": int(np.min(value_in)),
        "min_value_out": int(np.min(value_out)),
        "max_value_in": int(np.max(value_in)),
        "max_value_out": int(np.max(value_out)),
    }
    return ImageProcessResult(enhanced_rgb=enhanced_rgb, lut=frame_result.lut, stats=stats)
