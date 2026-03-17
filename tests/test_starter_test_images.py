from pathlib import Path


def test_build_starter_test_images_creates_manifest_and_eval_subset(tmp_path: Path):
    from ddic_ce.starter_test_images import StarterDatasetConfig, build_starter_test_images

    raw_root = tmp_path / "raw" / "starter_synth_v1"
    manifest_path = tmp_path / "derived" / "manifests" / "starter_manifest.csv"
    eval_subset_root = tmp_path / "derived" / "eval_subsets"

    summary = build_starter_test_images(
        StarterDatasetConfig(
            raw_root=raw_root,
            manifest_path=manifest_path,
            eval_subset_root=eval_subset_root,
            width=96,
            height=96,
        )
    )

    assert summary["image_count"] == 65
    assert manifest_path.exists()
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert "high_key_window_soft.png" in manifest_text
    assert "low_key_small_bright_sign_2pct.png" in manifest_text
    assert "color_bars_soft.png" in manifest_text
    assert "rgb_ramp_r_256_horizontal.png" in manifest_text
    assert "rgb_ramp_b_8_vertical.png" in manifest_text
    assert "gray_ramp_64_vertical.png" in manifest_text
    assert "color_bars_ebu_75_horizontal.png" in manifest_text
    assert "color_bars_gray_skin_mix_vertical.png" in manifest_text
    assert (eval_subset_root / "starter_synth_v1" / "high_key" / "high_key_window_soft.png").exists()
    assert (eval_subset_root / "starter_synth_v1" / "low_key" / "low_key_noise_room.png").exists()
    assert (eval_subset_root / "starter_synth_v1" / "normal" / "color_bars_soft.png").exists()
    assert (eval_subset_root / "starter_synth_v1" / "gradient" / "rgb_ramp_r_256_horizontal.png").exists()
    assert (eval_subset_root / "starter_synth_v1" / "gradient" / "gray_ramp_32_vertical.png").exists()
    assert (eval_subset_root / "starter_synth_v1" / "normal" / "color_bars_rgbcmykw_vertical.png").exists()


def test_starter_test_images_include_requested_ramps_and_color_bars():
    from ddic_ce.starter_test_images import STARTER_IMAGE_SPECS

    filenames = [spec.filename for spec in STARTER_IMAGE_SPECS]
    rgb_ramps = [name for name in filenames if name.startswith("rgb_ramp_")]
    gray_ramps = [name for name in filenames if name.startswith("gray_ramp_")]
    color_bars = [name for name in filenames if name.startswith("color_bars_") and name != "color_bars_soft.png"]

    assert len(rgb_ramps) == 24
    assert len(gray_ramps) == 8
    assert len(color_bars) == 8


def test_vscode_starter_dataset_entry_script_exposes_zero_arg_main():
    import build_starter_test_dataset

    assert callable(build_starter_test_dataset.main)


def test_scripts_starter_dataset_entry_script_exposes_zero_arg_main():
    import importlib.util
    from pathlib import Path

    script_path = Path("scripts/build_starter_test_dataset.py")
    spec = importlib.util.spec_from_file_location("scripts_build_starter_test_dataset", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert callable(module.main)
