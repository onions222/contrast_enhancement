import numpy as np
from dataclasses import dataclass

from ddic_ce.reference_model import ContrastConfig, ContrastReferenceModel


def rgb_to_luma(rgb: np.ndarray) -> np.ndarray:
    """把 RGB 图像转换成 8bit luma 平面。

    这里使用整数近似系数 `77/150/29`，与代码里其他 luma 统计路径保持一致，
    便于图像 I/O、模型输入和验证脚本之间对齐。
    """
    rgb_u16 = rgb.astype(np.uint16)
    y = (77 * rgb_u16[..., 0] + 150 * rgb_u16[..., 1] + 29 * rgb_u16[..., 2]) >> 8
    return y.astype(np.uint8)


def apply_luma_lut_to_rgb(rgb: np.ndarray, lut: list[int]) -> np.ndarray:
    """依据 luma LUT 推导逐像素 gain，并作用到 RGB 三通道。

    先计算输入 luma，再查表得到目标 luma，随后用 `y_out / y_in` 形成 gain。
    当输入 luma 为 0 时用 1 做分母保护，最终结果裁剪到 8bit RGB 范围。
    """
    y_in = rgb_to_luma(rgb)
    lut_array = np.asarray(lut, dtype=np.uint16)
    y_out = lut_array[y_in]
    gain = y_out.astype(np.float32) / np.maximum(y_in, 1).astype(np.float32)
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
    y_in = rgb_to_luma(rgb)
    frame_result = model.process_frame(y_in.reshape(-1).tolist())
    enhanced_rgb = apply_luma_lut_to_rgb(rgb, frame_result.lut)
    y_out = rgb_to_luma(enhanced_rgb)
    stats: dict[str, float | int] = {
        "mean_in": float(np.mean(y_in)),
        "mean_out": float(np.mean(y_out)),
        "min_in": int(np.min(y_in)),
        "min_out": int(np.min(y_out)),
        "max_in": int(np.max(y_in)),
        "max_out": int(np.max(y_out)),
    }
    return ImageProcessResult(enhanced_rgb=enhanced_rgb, lut=frame_result.lut, stats=stats)
