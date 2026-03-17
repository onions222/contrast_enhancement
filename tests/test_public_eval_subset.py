from pathlib import Path

import numpy as np
from PIL import Image


def _save_rgb(path: Path, value: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(value.astype(np.uint8)).save(path)


def test_build_public_eval_subset_selects_available_images_and_reports_missing_sources(tmp_path: Path):
    from ddic_ce.public_eval_subset import PublicEvalSubsetConfig, build_public_eval_subset

    raw_root = tmp_path / "raw"
    manifest_dir = tmp_path / "derived" / "manifests"
    eval_subset_root = tmp_path / "derived" / "eval_subsets"

    _save_rgb(raw_root / "mit_adobe_fivek" / "portrait_face_bright.png", np.full((16, 16, 3), 220, dtype=np.uint8))
    _save_rgb(raw_root / "bsds500" / "sky_gradient_wall.png", np.full((16, 16, 3), 180, dtype=np.uint8))
    low_key = np.full((16, 16, 3), 24, dtype=np.uint8)
    low_key[6:10, 6:10] = 200
    _save_rgb(raw_root / "exdark" / "night_sign_text.png", low_key)
    _save_rgb(raw_root / "text_in_the_dark" / "dark_text_board.png", low_key)
    gradient = np.repeat(np.linspace(96, 140, num=16, dtype=np.uint8)[None, :, None], 16, axis=0)
    gradient = np.repeat(gradient, 3, axis=2)
    _save_rgb(raw_root / "usc_sipi" / "smooth_gradient.png", gradient)

    summary = build_public_eval_subset(
        PublicEvalSubsetConfig(
            raw_root=raw_root,
            manifest_dir=manifest_dir,
            eval_subset_root=eval_subset_root,
        )
    )

    assert summary["master_entry_count"] == 5
    assert summary["selected_entry_count"] >= 4
    assert "sid" in summary["missing_sources"]
    assert Path(summary["selected_manifest_path"]).exists()
    assert Path(summary["summary_path"]).exists()
    assert (eval_subset_root / "public_first_batch" / "faces_skin" / "mit_adobe_fivek__portrait_face_bright.png").exists()
    assert (eval_subset_root / "public_first_batch" / "text_ui" / "text_in_the_dark__dark_text_board.png").exists()
    assert (eval_subset_root / "public_first_batch" / "gradient" / "usc_sipi__smooth_gradient.png").exists()


def test_public_subset_entry_script_exposes_zero_arg_main():
    import build_public_eval_subset

    assert callable(build_public_eval_subset.main)


def test_build_public_eval_subset_applies_wikimedia_curated_bucket_overrides(tmp_path: Path):
    import json

    from ddic_ce.public_eval_subset import PublicEvalSubsetConfig, build_public_eval_subset

    raw_root = tmp_path / "raw"
    manifest_dir = tmp_path / "derived" / "manifests"
    eval_subset_root = tmp_path / "derived" / "eval_subsets"

    image = np.full((16, 16, 3), 220, dtype=np.uint8)
    image[:, :4] = 150
    _save_rgb(raw_root / "wikimedia_commons" / "high_key_empty_apartment_room_window.jpg", image)
    (raw_root / "wikimedia_commons" / "2026-03-17-wikimedia_commons_curated.json").write_text(
        json.dumps(
            {
                "downloaded": [
                    {
                        "filename": "high_key_empty_apartment_room_window.jpg",
                        "expected_bucket": "high_key",
                        "expected_failure_modes": ["highlight_washout"],
                        "notes": "curated override",
                    }
                ],
                "failed": [],
            }
        ),
        encoding="utf-8",
    )

    summary = build_public_eval_subset(
        PublicEvalSubsetConfig(
            raw_root=raw_root,
            manifest_dir=manifest_dir,
            eval_subset_root=eval_subset_root,
        )
    )

    assert summary["bucket_summary"]["high_key"]["selected_count"] == 1
    assert (eval_subset_root / "public_first_batch" / "high_key" / "wikimedia_commons__high_key_empty_apartment_room_window.jpg").exists()


def test_build_public_eval_subset_prefers_explicit_low_light_noisy_override(tmp_path: Path):
    import json

    from ddic_ce.public_eval_subset import PublicEvalSubsetConfig, build_public_eval_subset

    raw_root = tmp_path / "raw"
    manifest_dir = tmp_path / "derived" / "manifests"
    eval_subset_root = tmp_path / "derived" / "eval_subsets"

    image = np.full((32, 32, 3), 12, dtype=np.uint8)
    image[:, 16:] = 230
    _save_rgb(raw_root / "wikimedia_commons" / "low_light_noisy_dark_room_night_mode_off.jpg", image)
    (raw_root / "wikimedia_commons" / "2026-03-17-wikimedia_commons_curated.json").write_text(
        json.dumps(
            {
                "downloaded": [
                    {
                        "filename": "low_light_noisy_dark_room_night_mode_off.jpg",
                        "expected_bucket": "low_light_noisy",
                        "expected_failure_modes": ["noise_boost"],
                        "notes": "curated low-light noisy override",
                    }
                ],
                "failed": [],
            }
        ),
        encoding="utf-8",
    )

    summary = build_public_eval_subset(
        PublicEvalSubsetConfig(
            raw_root=raw_root,
            manifest_dir=manifest_dir,
            eval_subset_root=eval_subset_root,
        )
    )

    assert summary["bucket_summary"]["low_light_noisy"]["selected_count"] == 1
    assert summary["bucket_summary"]["high_contrast"]["selected_count"] == 0
    assert (eval_subset_root / "public_first_batch" / "low_light_noisy" / "wikimedia_commons__low_light_noisy_dark_room_night_mode_off.jpg").exists()


def test_build_public_eval_subset_prefers_explicit_faces_skin_override_without_face_keywords(tmp_path: Path):
    import json

    from ddic_ce.public_eval_subset import PublicEvalSubsetConfig, build_public_eval_subset

    raw_root = tmp_path / "raw"
    manifest_dir = tmp_path / "derived" / "manifests"
    eval_subset_root = tmp_path / "derived" / "eval_subsets"

    image = np.full((32, 24, 3), 140, dtype=np.uint8)
    image[:, 8:16] = np.array([180, 120, 80], dtype=np.uint8)
    _save_rgb(raw_root / "wikimedia_commons" / "standing_subject_sample.jpg", image)
    (raw_root / "wikimedia_commons" / "2026-03-17-wikimedia_commons_curated.json").write_text(
        json.dumps(
            {
                "downloaded": [
                    {
                        "filename": "standing_subject_sample.jpg",
                        "expected_bucket": "faces_skin",
                        "expected_failure_modes": ["color_shift"],
                        "notes": "curated full-body dark-skin sample",
                    }
                ],
                "failed": [],
            }
        ),
        encoding="utf-8",
    )

    summary = build_public_eval_subset(
        PublicEvalSubsetConfig(
            raw_root=raw_root,
            manifest_dir=manifest_dir,
            eval_subset_root=eval_subset_root,
        )
    )

    assert summary["bucket_summary"]["faces_skin"]["selected_count"] == 1
    assert (eval_subset_root / "public_first_batch" / "faces_skin" / "wikimedia_commons__standing_subject_sample.jpg").exists()


def test_public_subset_faces_bucket_does_not_match_substrings_in_unrelated_words(tmp_path: Path):
    import json

    from ddic_ce.public_eval_subset import PublicEvalSubsetConfig, build_public_eval_subset

    raw_root = tmp_path / "raw"
    manifest_dir = tmp_path / "derived" / "manifests"
    eval_subset_root = tmp_path / "derived" / "eval_subsets"

    lounge = np.full((16, 16, 3), 40, dtype=np.uint8)
    lounge[:, 8:] = 180
    _save_rgb(raw_root / "wikimedia_commons" / "low_key_lobby_lounge_amantaka_suite_laos.jpg", lounge)
    fisherman = np.full((16, 16, 3), 230, dtype=np.uint8)
    fisherman[:, :4] = 10
    _save_rgb(raw_root / "wikimedia_commons" / "high_contrast_fisherman_pirogue_sunset_laos.jpg", fisherman)
    (raw_root / "wikimedia_commons" / "2026-03-17-wikimedia_commons_curated.json").write_text(
        json.dumps(
            {
                "downloaded": [
                    {
                        "filename": "low_key_lobby_lounge_amantaka_suite_laos.jpg",
                        "expected_bucket": "low_key",
                        "expected_failure_modes": ["shadow_crush"],
                        "notes": "low-key override",
                    },
                    {
                        "filename": "high_contrast_fisherman_pirogue_sunset_laos.jpg",
                        "expected_bucket": "high_contrast",
                        "expected_failure_modes": ["halo"],
                        "notes": "high-contrast override",
                    },
                ],
                "failed": [],
            }
        ),
        encoding="utf-8",
    )

    summary = build_public_eval_subset(
        PublicEvalSubsetConfig(
            raw_root=raw_root,
            manifest_dir=manifest_dir,
            eval_subset_root=eval_subset_root,
        )
    )

    assert summary["bucket_summary"]["faces_skin"]["selected_count"] == 0
    assert summary["bucket_summary"]["low_key"]["selected_count"] == 1
    assert summary["bucket_summary"]["high_contrast"]["selected_count"] == 1


def test_build_public_eval_subset_removes_stale_files_from_previous_runs(tmp_path: Path):
    import json

    from ddic_ce.public_eval_subset import PublicEvalSubsetConfig, build_public_eval_subset

    raw_root = tmp_path / "raw"
    manifest_dir = tmp_path / "derived" / "manifests"
    eval_subset_root = tmp_path / "derived" / "eval_subsets"
    stale_file = eval_subset_root / "public_first_batch" / "faces_skin" / "wikimedia_commons__old_landscape.jpg"
    stale_file.parent.mkdir(parents=True, exist_ok=True)
    stale_file.write_bytes(b"stale")

    image = np.full((16, 16, 3), 180, dtype=np.uint8)
    _save_rgb(raw_root / "wikimedia_commons" / "faces_skin_closeup_blonde_girl.jpg", image)
    (raw_root / "wikimedia_commons" / "2026-03-17-wikimedia_commons_curated.json").write_text(
        json.dumps(
            {
                "downloaded": [
                    {
                        "filename": "faces_skin_closeup_blonde_girl.jpg",
                        "expected_bucket": "faces_skin",
                        "expected_failure_modes": ["color_shift"],
                        "notes": "portrait override",
                    }
                ],
                "failed": [],
            }
        ),
        encoding="utf-8",
    )

    build_public_eval_subset(
        PublicEvalSubsetConfig(
            raw_root=raw_root,
            manifest_dir=manifest_dir,
            eval_subset_root=eval_subset_root,
        )
    )

    assert not stale_file.exists()
    assert (eval_subset_root / "public_first_batch" / "faces_skin" / "wikimedia_commons__faces_skin_closeup_blonde_girl.jpg").exists()
