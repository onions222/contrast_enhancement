from pathlib import Path

import numpy as np
from PIL import Image

from ddic_ce.batch_runner import run_batch
from ddic_ce.reference_model import ContrastConfig


def test_run_batch_writes_enhanced_images_and_summary(tmp_path: Path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    img = np.array([[[0, 0, 0], [255, 255, 255]]], dtype=np.uint8)
    Image.fromarray(img).save(input_dir / "sample.png")

    run_batch(input_dir, output_dir, ContrastConfig())

    assert (output_dir / "enhanced" / "sample.png").exists()
    assert (output_dir / "lut" / "sample.csv").exists()
    assert (output_dir / "meta" / "sample.json").exists()
    assert (output_dir / "summary.csv").exists()


def test_build_arg_parser_accepts_required_paths():
    from ddic_ce.batch_runner import build_arg_parser

    parser = build_arg_parser()
    args = parser.parse_args(["in_dir", "out_dir"])
    assert args.input_dir == "in_dir"
    assert args.output_dir == "out_dir"
