from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _export() -> dict:
    sys.path.insert(0, str(_repo_root() / "scheme1" / "src"))
    from ce_scheme1.percentile_pwl import FloatPercentilePwlConfig, FloatPercentilePwlModel

    cfg = FloatPercentilePwlConfig()
    cases = [
        ("empty_identity", [[]]),
        ("tri_peak", [[32, 32, 32, 96, 96, 96, 160, 160, 160]]),
        ("narrow_range", [[120, 120, 120, 122, 122, 122, 124, 124, 124]]),
        (
            "temporal_pair",
            [
                [32, 32, 32, 128, 128, 128, 196, 196, 196],
                [40, 40, 40, 136, 136, 136, 204, 204, 204],
            ],
        ),
    ]

    report: dict[str, object] = {"cases": []}
    for case_name, frames in cases:
        model = FloatPercentilePwlModel(cfg)
        exported_frames = []
        for index, frame in enumerate(frames):
            result = model.process_frame(frame)
            gain_nominal_q8 = int(math.floor(result.stats["gain_nominal"] * 256.0 + 1e-9))
            gain_q8 = int(math.floor(result.stats["gain"] * 256.0 + 1e-9))
            anchor_low = int(result.pwl_knots[1][0]) if len(result.pwl_knots) >= 4 else 0
            anchor_high = int(result.pwl_knots[3][0]) if len(result.pwl_knots) >= 4 else 255
            exported_frames.append(
                {
                    "name": f"{case_name}_frame_{index}",
                    "histogram32": [int(v) for v in result.histogram],
                    "lut": [int(v) for v in result.lut],
                    "mapped_samples": [int(v) for v in result.mapped_samples],
                    "p_low": int(round(result.stats["p_low"])),
                    "p_high": int(round(result.stats["p_high"])),
                    "anchor_low": anchor_low,
                    "anchor_high": anchor_high,
                    "gain_nominal_q8": gain_nominal_q8,
                    "gain_q8": gain_q8,
                }
            )
        report["cases"].append({"name": case_name, "frames": exported_frames})
    return report


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: export_percentile_pwl_reference.py <output-json>")

    output_path = Path(sys.argv[1])
    output_path.write_text(json.dumps(_export(), ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
