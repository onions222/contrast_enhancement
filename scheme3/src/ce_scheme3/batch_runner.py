import argparse
import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image

from ce_scheme3.image_io import process_rgb_image
from ce_scheme3.reference_model import ContrastConfig

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}


def _write_lut_csv(path: Path, lut: list[int]) -> None:
    """把单张图像对应的 LUT 导出为两列表格。"""
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["index", "value"])
        for idx, value in enumerate(lut):
            writer.writerow([idx, value])


def run_batch(input_dir: Path, output_dir: Path, cfg: ContrastConfig) -> None:
    """批量处理目录中的图像，并导出增强图、LUT 与统计摘要。"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    enhanced_dir = output_path / "enhanced"
    lut_dir = output_path / "lut"
    meta_dir = output_path / "meta"
    enhanced_dir.mkdir(parents=True, exist_ok=True)
    lut_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict[str, str | int | float]] = []
    for image_path in sorted(input_path.iterdir()):
        if image_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        rgb = np.asarray(Image.open(image_path).convert("RGB"), dtype=np.uint8)
        result = process_rgb_image(rgb, cfg)

        Image.fromarray(result.enhanced_rgb).save(enhanced_dir / image_path.name)
        _write_lut_csv(lut_dir / f"{image_path.stem}.csv", result.lut)

        meta = {
            "filename": image_path.name,
            "width": int(rgb.shape[1]),
            "height": int(rgb.shape[0]),
            "n_bins": cfg.n_bins,
            "clip_gain": cfg.clip_gain,
            **result.stats,
        }
        with (meta_dir / f"{image_path.stem}.json").open("w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)
        summary_rows.append(meta)

    summary_path = output_path / "summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = [
            "filename",
            "width",
            "height",
            "n_bins",
            "clip_gain",
            "mean_in",
            "mean_out",
            "min_in",
            "min_out",
            "max_in",
            "max_out",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)


def build_arg_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="Run DDIC self-LUT image batch evaluation.")
    parser.add_argument("input_dir")
    parser.add_argument("output_dir")
    parser.add_argument("--bins", type=int, choices=(32, 64), default=32)
    parser.add_argument("--clip-gain", type=float, default=2.0)
    parser.add_argument("--alpha-num", type=int, default=1)
    parser.add_argument("--alpha-den", type=int, default=8)
    return parser


def main(argv: list[str] | None = None) -> int:
    """命令行入口：解析参数、构造配置并执行批处理。"""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    cfg = ContrastConfig(
        n_bins=args.bins,
        clip_gain=args.clip_gain,
        alpha_num=args.alpha_num,
        alpha_den=args.alpha_den,
    )
    run_batch(Path(args.input_dir), Path(args.output_dir), cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
