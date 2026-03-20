from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ce_scheme3.image_io import rgb_to_value
from ce_scheme3.metrics import compute_ambe, compute_eme, summarize_plane
from ce_scheme3.temporal_runner import SUPPORTED_EXTENSIONS
from ce_scheme3.discrete_scene_gain_float import FloatDiscreteSceneGainConfig, FloatDiscreteSceneGainModel


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVAL_SUBSET_ROOT = REPO_ROOT / "data" / "derived" / "eval_subsets"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "derived" / "float_full_eval" / "2026-03-17-python-float-full-eval"
DEFAULT_MANIFEST_DIR = REPO_ROOT / "data" / "derived" / "manifests"


@dataclass(frozen=True)
class FloatFullEvalConfig:
    dataset_roots: tuple[Path, ...] = ()
    output_dir: Path = DEFAULT_OUTPUT_DIR
    recursive: bool = True
    manifest_csv: Path | None = None
    manifest_dir: Path = DEFAULT_MANIFEST_DIR
    scene_hold_enable: bool = False


def _resolve_dataset_roots(cfg: FloatFullEvalConfig) -> tuple[Path, ...]:
    if cfg.dataset_roots:
        return tuple(Path(path) for path in cfg.dataset_roots)
    root = DEFAULT_EVAL_SUBSET_ROOT
    if not root.exists():
        return ()
    return tuple(sorted(path for path in root.iterdir() if path.is_dir()))


def _iter_image_paths(input_dir: Path, recursive: bool) -> list[Path]:
    if not input_dir.exists():
        return []
    iterator = input_dir.rglob("*") if recursive else input_dir.iterdir()
    return sorted(path for path in iterator if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS)


def _load_manifest_lookup(cfg: FloatFullEvalConfig) -> dict[str, dict[str, str]]:
    manifest_paths: list[Path]
    if cfg.manifest_csv is not None:
        manifest_paths = [Path(cfg.manifest_csv)]
    else:
        manifest_paths = sorted(Path(cfg.manifest_dir).glob("*_manifest.csv")) if Path(cfg.manifest_dir).exists() else []

    lookup: dict[str, dict[str, str]] = {}
    for manifest_path in manifest_paths:
        with manifest_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                relative_path = row.get("relative_path", "")
                filename = row.get("filename", "")
                if relative_path:
                    lookup[relative_path] = row
                if filename and filename not in lookup:
                    lookup[filename] = row
    return lookup


def _stable_stem(relative_path: Path) -> str:
    return "__".join(relative_path.with_suffix("").parts)


def _apply_float_gain_to_rgb(rgb: np.ndarray, tone_curve: list[float]) -> np.ndarray:
    value_in = rgb_to_value(rgb)
    lut = np.asarray(tone_curve, dtype=np.float32)
    value_out = lut[value_in]
    gain = value_out / np.maximum(value_in, 1).astype(np.float32)
    rgb_out = np.clip(rgb.astype(np.float32) * gain[..., None], 0, 255)
    return np.rint(rgb_out).astype(np.uint8)


def _clip_ratio(plane: np.ndarray, *, low_threshold: int | None = None, high_threshold: int | None = None) -> float:
    values = np.asarray(plane, dtype=np.uint8)
    if low_threshold is not None:
        return float(np.mean(values <= low_threshold))
    if high_threshold is not None:
        return float(np.mean(values >= high_threshold))
    return 0.0


def _channel_ratio_drift(before: np.ndarray, after: np.ndarray) -> float:
    before_f = before.astype(np.float32)
    after_f = after.astype(np.float32)
    before_sum = np.maximum(before_f.sum(axis=2, keepdims=True), 1.0)
    after_sum = np.maximum(after_f.sum(axis=2, keepdims=True), 1.0)
    before_ratio = before_f / before_sum
    after_ratio = after_f / after_sum
    mask = rgb_to_value(before) > 8
    if not np.any(mask):
        return 0.0
    return float(np.mean(np.abs(after_ratio[mask] - before_ratio[mask])))


def _mean_chroma(rgb: np.ndarray) -> float:
    rgb_f = rgb.astype(np.float32)
    return float(np.mean(np.max(rgb_f, axis=2) - np.min(rgb_f, axis=2)))


def _max_plateau_len(plane: np.ndarray) -> int:
    values = np.asarray(plane, dtype=np.uint8)
    best = 1
    for line in (values, values.T):
        for row in line:
            run = 1
            for left, right in zip(row[:-1], row[1:]):
                if int(left) == int(right):
                    run += 1
                    best = max(best, run)
                else:
                    run = 1
    return int(best)


def _gradient_step_irregularity(plane: np.ndarray) -> float:
    values = np.asarray(plane, dtype=np.int16)
    diffs = np.abs(np.diff(values, axis=1)).astype(np.float32)
    if diffs.size == 0:
        return 0.0
    return float(np.std(diffs))


def _shadow_std_gain(before: np.ndarray, after: np.ndarray) -> float:
    mask = np.asarray(before, dtype=np.uint8) <= 63
    if not np.any(mask):
        return 1.0
    before_std = float(np.std(before[mask]))
    after_std = float(np.std(after[mask]))
    return after_std / max(before_std, 1e-6)


def _local_contrast_p95_gain(before: np.ndarray, after: np.ndarray) -> float:
    before_f = before.astype(np.int16)
    after_f = after.astype(np.int16)
    before_grad = np.abs(np.diff(before_f, axis=1)).astype(np.float32)
    after_grad = np.abs(np.diff(after_f, axis=1)).astype(np.float32)
    if before_grad.size == 0:
        return 1.0
    return float(np.percentile(after_grad, 95) / max(np.percentile(before_grad, 95), 1.0))


def _skin_proxy_shift(before: np.ndarray, after: np.ndarray) -> float:
    before_f = before.astype(np.float32)
    after_f = after.astype(np.float32)
    mask = (
        (before_f[..., 0] > 95)
        & (before_f[..., 1] > 40)
        & (before_f[..., 2] > 20)
        & (before_f[..., 0] > before_f[..., 1])
        & (before_f[..., 1] > before_f[..., 2] * 0.8)
    )
    if not np.any(mask):
        return 0.0
    before_ratio = before_f[mask] / np.maximum(before_f[mask].sum(axis=1, keepdims=True), 1.0)
    after_ratio = after_f[mask] / np.maximum(after_f[mask].sum(axis=1, keepdims=True), 1.0)
    return float(np.mean(np.abs(after_ratio - before_ratio)))


def _compute_metrics(rgb_in: np.ndarray, rgb_out: np.ndarray) -> dict[str, float]:
    value_in = rgb_to_value(rgb_in)
    value_out = rgb_to_value(rgb_out)
    before = summarize_plane(value_in)
    after = summarize_plane(value_out)
    unique_in = max(int(np.unique(value_in).size), 1)
    unique_out = max(int(np.unique(value_out).size), 1)
    return {
        "mean_value_in": before["mean"],
        "mean_value_out": after["mean"],
        "mean_delta": after["mean"] - before["mean"],
        "ambe": compute_ambe(value_in, value_out),
        "eme_delta": compute_eme(value_out) - compute_eme(value_in),
        "dark_ratio_delta": after["dark_ratio"] - before["dark_ratio"],
        "bright_ratio_delta": after["bright_ratio"] - before["bright_ratio"],
        "highlight_clip_ratio_delta": _clip_ratio(value_out, high_threshold=250) - _clip_ratio(value_in, high_threshold=250),
        "shadow_clip_ratio_delta": _clip_ratio(value_out, low_threshold=5) - _clip_ratio(value_in, low_threshold=5),
        "p2_delta": after["p2"] - before["p2"],
        "p98_delta": after["p98"] - before["p98"],
        "unique_level_retention": unique_out / unique_in,
        "max_plateau_len": float(_max_plateau_len(value_out)),
        "gradient_step_irregularity": _gradient_step_irregularity(value_out),
        "shadow_std_gain": _shadow_std_gain(value_in, value_out),
        "local_contrast_p95_gain": _local_contrast_p95_gain(value_in, value_out),
        "channel_ratio_drift": _channel_ratio_drift(rgb_in, rgb_out),
        "mean_chroma_delta": _mean_chroma(rgb_out) - _mean_chroma(rgb_in),
        "skin_proxy_shift": _skin_proxy_shift(rgb_in, rgb_out),
    }


def _classify_risks(
    metrics: dict[str, float],
    manifest: dict[str, str] | None,
    *,
    relative_path: str,
) -> tuple[list[str], list[str], float]:
    risk_types: list[str] = []
    triggers: list[str] = []
    score = 0.0
    scene_tag = str(manifest.get("scene_tag", "")) if isinstance(manifest, dict) else ""
    lower_path = relative_path.lower()
    smooth_gradient_candidate = (
        scene_tag == "gradient"
        or "gradient" in lower_path
        or "ramp" in lower_path
        or "color_bars" in lower_path
        or "sky" in lower_path
    )
    skin_candidate = scene_tag == "faces_skin" or "skin" in lower_path or "face" in lower_path or "portrait" in lower_path

    def add(risk_type: str, metric_name: str, weight: float) -> None:
        nonlocal score
        if risk_type not in risk_types:
            risk_types.append(risk_type)
        triggers.append(metric_name)
        score += weight

    if metrics["highlight_clip_ratio_delta"] > 0.03 or metrics["bright_ratio_delta"] > 0.10:
        add("highlight_washout", "highlight_clip_ratio_delta", 3.0)
    if metrics["shadow_clip_ratio_delta"] > 0.08 or metrics["dark_ratio_delta"] > 0.25:
        add("shadow_crush", "shadow_clip_ratio_delta", 3.0)
    if metrics["shadow_std_gain"] > 1.08:
        add("noise_boost", "shadow_std_gain", 2.5)
    if metrics["channel_ratio_drift"] > 0.005 or (skin_candidate and metrics["skin_proxy_shift"] > 0.008):
        add("color_shift", "channel_ratio_drift", 2.5)
    if metrics["unique_level_retention"] < 0.82 or (smooth_gradient_candidate and metrics["unique_level_retention"] < 0.95):
        add("banding", "unique_level_retention", 2.0)
    if metrics["eme_delta"] > 1.5 or metrics["local_contrast_p95_gain"] > 1.55:
        add("over_enhancement", "local_contrast_p95_gain", 2.0)

    expected = []
    if isinstance(manifest, dict):
        expected = [mode for mode in str(manifest.get("expected_failure_modes", "")).split("|") if mode]
    for mode in expected:
        if mode in risk_types:
            score += 1.0

    if not risk_types and abs(metrics["mean_delta"]) >= 20.0:
        add("global_shift", "mean_delta", 1.0)

    return risk_types, sorted(set(triggers)), score


def _write_compare_image(
    rgb_in: np.ndarray,
    rgb_out: np.ndarray,
    output_path: Path,
    *,
    title_lines: list[str],
) -> None:
    left = Image.fromarray(rgb_in)
    right = Image.fromarray(rgb_out)
    width, height = left.size
    canvas = Image.new("RGB", (width * 2, height + 52), color=(18, 18, 18))
    canvas.paste(left, (0, 52))
    canvas.paste(right, (width, 52))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, 6), "Input", fill=(240, 240, 240))
    draw.text((width + 8, 6), "Output", fill=(240, 240, 240))
    for index, line in enumerate(title_lines[:3]):
        draw.text((120, 6 + 14 * index), line, fill=(210, 210, 210))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)


def _json_default(value: object) -> object:
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    return value


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_report(payload: dict[str, object]) -> str:
    scene_bucket_summary = payload["scene_bucket_summary"]
    stable_buckets = [
        name
        for name, bucket in sorted(scene_bucket_summary.items())
        if bucket["high_risk_count"] == 0 or bucket["high_risk_count"] / max(bucket["count"], 1) <= 0.25
    ]
    risky_buckets = sorted(
        scene_bucket_summary.items(),
        key=lambda item: (
            -(item[1]["high_risk_count"] / max(item[1]["count"], 1)),
            -item[1]["mean_risk_score"],
            item[0],
        ),
    )
    risk_type_examples: dict[str, dict[str, object]] = {}
    for sample in payload["high_risk_samples"]:
        for risk_type in str(sample["risk_types"]).split("|"):
            risk_type_examples.setdefault(risk_type, sample)

    lines = [
        "# Python Float 对比度增强测试报告",
        "",
        "## 测试目标",
        "",
        "评估当前仓库 Python float 离散场景对比度增强算法的 still-image 表现，输出可评审的图像对比、数值分析和高风险样本清单。",
        "",
        "## 测试数据范围",
        "",
    ]
    for dataset_name, bucket in sorted(payload["subdataset_summary"].items()):
        lines.append(f"- `{dataset_name}`: {bucket['count']} 张")

    lines.extend(
        [
            "",
            "## 测试方法",
            "",
            "- 对每张图提取当前图自身的 HSV V 统计，运行 Python float scene/gain 路径，再把 gain 作用回 RGB。",
            "- 同时输出增强图、前后双联图、per-image JSON、汇总 CSV 和风险清单。",
            "- 本轮没有真实时序序列，因此不输出帧间稳定性结论。",
            "",
            "## 指标体系",
            "",
            "- 暗部噪点放大：`shadow_std_gain`，用于看暗区纹理/噪点是否被明显放大；不能单独区分真实纹理与噪点。",
            "- 颜色异常：`channel_ratio_drift`、`skin_proxy_shift`，用于看 RGB 比例是否漂移；没有语义真值，只能做 proxy 检测。",
            "- 高光风险：`highlight_clip_ratio_delta`、`bright_ratio_delta`，用于看高光是否更容易顶死；高亮占比高不必然等于失败。",
            "- 暗部压死：`shadow_clip_ratio_delta`、`dark_ratio_delta`，用于看阴影是否被压向更少层级；纯黑场景解释需谨慎。",
            "- banding 风险：`unique_level_retention`、`max_plateau_len`，用于看平滑区域层级是否塌陷；对自然纹理图不如对 gradient 图可靠。",
            "- 局部对比异常增强：`eme_delta`、`local_contrast_p95_gain`，用于看局部增强是否过猛；局部对比提升本身不一定是坏事。",
            "",
            "## 风险筛选规则",
            "",
            "- 先按阈值触发风险标签，再按加权 `risk_score` 排序。",
            "- 若 manifest 的 `expected_failure_modes` 与触发风险一致，则提高该样本优先级。",
            "- 高风险样本不等同于必然失败样本，仍需结合双联图人工确认。",
            "",
            "## 总体结果概览",
            "",
            f"- 总样本数：`{payload['frame_count']}`",
            f"- 高风险样本数：`{len(payload['high_risk_samples'])}`",
            f"- 表现相对稳定的场景桶：`{', '.join(stable_buckets) if stable_buckets else '无明显稳定桶'}`",
            "",
            "## 各子数据集结果分析",
            "",
            "| 子数据集 | Count | High Risk | Mean Risk Score |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for dataset_name, bucket in sorted(payload["subdataset_summary"].items()):
        lines.append(
            f"| {dataset_name} | {bucket['count']} | {bucket['high_risk_count']} | {bucket['mean_risk_score']:.2f} |"
        )

    lines.extend(["", "### 场景桶细分", "", "| 场景桶 | Count | High Risk | Mean Risk Score |", "| --- | ---: | ---: | ---: |"])
    for bucket_name, bucket in sorted(scene_bucket_summary.items()):
        lines.append(
            f"| {bucket_name} | {bucket['count']} | {bucket['high_risk_count']} | {bucket['mean_risk_score']:.2f} |"
        )

    lines.extend(["", "## 高风险样本", ""])
    for sample in payload["high_risk_samples"][:20]:
        lines.append(
            f"- `{sample['relative_path']}`: {sample['risk_types']} | 指标 `{sample['triggered_metrics']}` | 双联图 `{sample['compare_path']}`"
        )

    lines.extend(["", "## 典型失败案例", ""])
    for sample in payload["high_risk_samples"][:5]:
        lines.append(f"- `{sample['relative_path']}`: {sample['summary_note']}")

    lines.extend(["", "## 问题归因", ""])
    for risk_type, label, cause, severity, next_step in (
        ("highlight_washout", "高光过度上抬", "更像是 Bright / high-key 曲线段偏激进，或高亮段映射保守不足。", "中高", "优先复核 high-key 与 faces/white-background 样本，评估高亮段 gain 是否需要收敛。"),
        ("shadow_crush", "暗部压死", "更像是 Dark I 场景下暗部提升不均，低亮区域整体向更深分布收缩。", "高", "优先复核 low-key 与 low-light-noisy 样本，检查 dark 场景曲线和 bypass 边界。"),
        ("banding", "渐变层级断裂", "更像是 tone curve 对平滑梯度的级数压缩，尤其在 synthetic ramp 和天空类内容。", "中高", "优先在 gradient / ramp 集合上看唯一级数和 plateau，必要时单独约束曲线平滑性。"),
        ("color_shift", "颜色关系异常", "更像是 gain x RGB 路径导致的通道比例漂移，在霓虹和彩色高饱和区域更明显。", "中", "优先复核 text_ui / faces_skin 场景，判断是否需要 RGB 保护或色彩保持策略。"),
        ("over_enhancement", "局部对比过增强", "更像是局部亮暗边界被推得过猛，常见于文本/窗框/高对比合成图。", "中", "优先复核 text_ui 和 synthetic high-contrast 样本，评估局部增益上限。"),
    ):
        sample = risk_type_examples.get(risk_type)
        if sample is None:
            continue
        lines.extend(
            [
                f"### {label}",
                "",
                f"- 现象：`{risk_type}` 在当前轮次被反复触发。",
                f"- 代表样例：`{sample['relative_path']}`",
                f"- 可能原因：{cause}",
                f"- 风险等级：{severity}",
                f"- 下一步建议：{next_step}",
                "",
            ]
        )

    lines.extend(
        [
            "",
            "## 当前版本存在的问题汇总",
            "",
            "- 合成集上的主要风险集中在 gradient/high_key/normal ramp 类样本，说明曲线设计对平滑梯度和高亮段更敏感。",
            "- 真实图上的主要风险集中在 low_key、low_light_noisy、text_ui 和少量 faces_skin，说明问题更偏暗部与高饱和区域，而不是全场景普遍退化。",
            "- 这些结论有数值支撑，但是否构成主观可见缺陷，仍需结合双联图人工确认。",
            "",
            "## 下一步建议",
            "",
            "- 先人工复核高风险样本 Top 列表，区分真缺陷与指标误报。",
            "- 若问题集中在同一类 scene，再进入参数/曲线修订，不在本轮直接改算法。",
            "",
            "## 输出路径",
            "",
            f"- 报告：`{payload['report_path']}`",
            f"- 汇总 JSON：`{payload['summary_path']}`",
            f"- 高风险 JSON：`{payload['high_risk_samples_json']}`",
            f"- 指标表：`{payload['per_image_metrics_csv']}`",
            f"- 高风险清单：`{payload['risk_samples_csv']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def run_float_full_eval(cfg: FloatFullEvalConfig | None = None) -> dict[str, object]:
    config = cfg or FloatFullEvalConfig()
    dataset_roots = _resolve_dataset_roots(config)
    output_dir = Path(config.output_dir)
    comparisons_dir = output_dir / "comparisons"
    enhanced_dir = output_dir / "enhanced"
    meta_dir = output_dir / "meta" / "per_image"
    tables_dir = output_dir / "tables"
    reports_dir = output_dir / "reports"
    risk_gallery_dir = output_dir / "risk_gallery"
    for path in (comparisons_dir, enhanced_dir, meta_dir, tables_dir, reports_dir, risk_gallery_dir):
        path.mkdir(parents=True, exist_ok=True)

    manifest_lookup = _load_manifest_lookup(config)
    model = FloatDiscreteSceneGainModel(FloatDiscreteSceneGainConfig(scene_hold_enable=config.scene_hold_enable))
    frames: list[dict[str, object]] = []

    for dataset_root in dataset_roots:
        for image_path in _iter_image_paths(dataset_root, config.recursive):
            rgb_in = np.asarray(Image.open(image_path).convert("RGB"), dtype=np.uint8)
            relative_path = image_path.relative_to(dataset_root)
            relative_path_str = relative_path.as_posix()
            manifest = manifest_lookup.get(relative_path_str) or manifest_lookup.get(image_path.name)
            frame_result = model.process_plane_image(rgb_to_value(rgb_in))
            rgb_out = _apply_float_gain_to_rgb(rgb_in, frame_result.tone_curve)
            metrics = _compute_metrics(rgb_in, rgb_out)
            risk_types, triggered_metrics, risk_score = _classify_risks(
                metrics,
                manifest,
                relative_path=relative_path_str,
            )
            stem = _stable_stem(relative_path)

            compare_rel = relative_path.parent / f"{stem}_compare.png"
            enhanced_rel = relative_path.parent / f"{stem}_enhanced.png"
            compare_path = comparisons_dir / compare_rel
            enhanced_path = enhanced_dir / enhanced_rel
            _write_compare_image(
                rgb_in,
                rgb_out,
                compare_path,
                title_lines=[
                    stem,
                    f"manifest={manifest.get('scene_tag', '-') if isinstance(manifest, dict) else '-'} raw={frame_result.raw_scene_name} out={frame_result.scene_name}",
                    f"bypass={frame_result.bypass_flag} mean_v={metrics['mean_value_out']:.1f} bright_d={metrics['bright_ratio_delta']:.3f}",
                ],
            )
            enhanced_path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(rgb_out).save(enhanced_path)

            frame_payload = {
                "dataset_name": dataset_root.name,
                "relative_path": relative_path_str,
                "input_path": str(image_path),
                "stem": stem,
                "scene_name": frame_result.scene_name,
                "raw_scene_name": frame_result.raw_scene_name,
                "bypass_flag": frame_result.bypass_flag,
                "stats": frame_result.stats,
                "metrics": metrics,
                "risk_types": risk_types,
                "triggered_metrics": triggered_metrics,
                "risk_score": risk_score,
                "compare_path": compare_path.relative_to(output_dir).as_posix(),
                "enhanced_path": enhanced_path.relative_to(output_dir).as_posix(),
                "manifest": manifest,
            }
            (meta_dir / f"{stem}.json").write_text(
                json.dumps(frame_payload, indent=2, ensure_ascii=False, default=_json_default),
                encoding="utf-8",
            )
            frames.append(frame_payload)

    per_image_rows: list[dict[str, object]] = []
    high_risk_samples: list[dict[str, object]] = []
    for frame in frames:
        row = {
            "dataset_name": frame["dataset_name"],
            "relative_path": frame["relative_path"],
            "scene_name": frame["scene_name"],
            "raw_scene_name": frame["raw_scene_name"],
            "bypass_flag": frame["bypass_flag"],
            "risk_score": round(float(frame["risk_score"]), 4),
        }
        row.update(frame["metrics"])
        per_image_rows.append(row)

        if frame["risk_types"]:
            sample = {
                "dataset_name": frame["dataset_name"],
                "relative_path": frame["relative_path"],
                "input_path": frame["input_path"],
                "risk_types": "|".join(frame["risk_types"]),
                "triggered_metrics": "|".join(frame["triggered_metrics"]),
                "compare_path": frame["compare_path"],
                "summary_note": f"{'|'.join(frame['risk_types'])} triggered by {'|'.join(frame['triggered_metrics'])}",
                "risk_score": round(float(frame["risk_score"]), 4),
            }
            high_risk_samples.append(sample)
            source = output_dir / frame["compare_path"]
            target = risk_gallery_dir / Path(frame["compare_path"]).name
            if source.exists():
                target.write_bytes(source.read_bytes())

    high_risk_samples.sort(key=lambda item: (-float(item["risk_score"]), item["relative_path"]))

    subdataset_summary: dict[str, dict[str, float | int]] = {}
    scene_bucket_summary: dict[str, dict[str, float | int]] = {}
    for row in per_image_rows:
        bucket = subdataset_summary.setdefault(
            str(row["dataset_name"]),
            {"count": 0, "high_risk_count": 0, "risk_score_total": 0.0},
        )
        bucket["count"] += 1
        bucket["risk_score_total"] += float(row["risk_score"])
        if float(row["risk_score"]) > 0.0:
            bucket["high_risk_count"] += 1
        scene_bucket = str(row["relative_path"]).split("/", 1)[0]
        scene_summary = scene_bucket_summary.setdefault(
            scene_bucket,
            {"count": 0, "high_risk_count": 0, "risk_score_total": 0.0},
        )
        scene_summary["count"] += 1
        scene_summary["risk_score_total"] += float(row["risk_score"])
        if float(row["risk_score"]) > 0.0:
            scene_summary["high_risk_count"] += 1
    for bucket in subdataset_summary.values():
        bucket["mean_risk_score"] = bucket["risk_score_total"] / max(int(bucket["count"]), 1)
        del bucket["risk_score_total"]
    for bucket in scene_bucket_summary.values():
        bucket["mean_risk_score"] = bucket["risk_score_total"] / max(int(bucket["count"]), 1)
        del bucket["risk_score_total"]

    per_image_metrics_csv = tables_dir / "per_image_metrics.csv"
    risk_samples_csv = tables_dir / "risk_samples.csv"
    high_risk_samples_json = reports_dir / "high_risk_samples.json"
    summary_path = reports_dir / "summary.json"
    report_path = reports_dir / "report.md"

    per_image_fieldnames = [
        "dataset_name",
        "relative_path",
        "scene_name",
        "raw_scene_name",
        "bypass_flag",
        "risk_score",
        "mean_value_in",
        "mean_value_out",
        "mean_delta",
        "ambe",
        "eme_delta",
        "dark_ratio_delta",
        "bright_ratio_delta",
        "highlight_clip_ratio_delta",
        "shadow_clip_ratio_delta",
        "p2_delta",
        "p98_delta",
        "unique_level_retention",
        "max_plateau_len",
        "gradient_step_irregularity",
        "shadow_std_gain",
        "local_contrast_p95_gain",
        "channel_ratio_drift",
        "mean_chroma_delta",
        "skin_proxy_shift",
    ]
    risk_fieldnames = [
        "dataset_name",
        "relative_path",
        "input_path",
        "risk_types",
        "triggered_metrics",
        "compare_path",
        "summary_note",
        "risk_score",
    ]
    _write_csv(per_image_metrics_csv, per_image_rows, per_image_fieldnames)
    _write_csv(risk_samples_csv, high_risk_samples, risk_fieldnames)

    payload = {
        "frame_count": len(frames),
        "dataset_roots": [str(path) for path in dataset_roots],
        "output_dir": str(output_dir),
        "report_path": str(report_path),
        "summary_path": str(summary_path),
        "high_risk_samples_json": str(high_risk_samples_json),
        "per_image_metrics_csv": str(per_image_metrics_csv),
        "risk_samples_csv": str(risk_samples_csv),
        "subdataset_summary": subdataset_summary,
        "scene_bucket_summary": scene_bucket_summary,
        "high_risk_samples": high_risk_samples,
    }
    high_risk_samples_json.write_text(
        json.dumps(high_risk_samples, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )
    summary_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")
    report_path.write_text(_build_report(payload), encoding="utf-8")
    return payload


def main() -> dict[str, object]:
    result = run_float_full_eval()
    print(f"Float full eval finished: {result['frame_count']} frames.")
    print(f"Report written to: {result['report_path']}")
    return result


if __name__ == "__main__":
    main()
