from pathlib import Path


def test_sync_dataset_repo_copies_raw_and_curated_assets(tmp_path: Path):
    from ddic_ce.dataset_repo_sync import DatasetRepoSyncConfig, sync_dataset_repo

    source_repo_root = tmp_path / "contrast"
    target_repo_root = tmp_path / "contrast-dataset"

    (source_repo_root / "data" / "raw" / "wikimedia_commons").mkdir(parents=True, exist_ok=True)
    (source_repo_root / "data" / "derived" / "manifests").mkdir(parents=True, exist_ok=True)
    (source_repo_root / "data" / "derived" / "eval_subsets").mkdir(parents=True, exist_ok=True)
    (source_repo_root / "data" / "derived" / "float_manual_eval").mkdir(parents=True, exist_ok=True)

    (source_repo_root / "data" / "raw" / "wikimedia_commons" / "sample.jpg").write_bytes(b"raw-image")
    (source_repo_root / "data" / "derived" / "manifests" / "manifest.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (source_repo_root / "data" / "derived" / "eval_subsets" / "subset.txt").write_text("subset", encoding="utf-8")
    (source_repo_root / "data" / "derived" / "float_manual_eval" / "summary.json").write_text("{}", encoding="utf-8")

    summary = sync_dataset_repo(
        DatasetRepoSyncConfig(
            source_repo_root=source_repo_root,
            target_repo_root=target_repo_root,
        )
    )

    assert summary["raw_files_copied"] == 1
    assert summary["manifest_files_copied"] == 1
    assert summary["subset_files_copied"] == 1
    assert (target_repo_root / "README.md").exists()
    assert (target_repo_root / ".gitignore").exists()
    assert (target_repo_root / "data" / "raw" / "wikimedia_commons" / "sample.jpg").read_bytes() == b"raw-image"
    assert (target_repo_root / "data" / "derived" / "manifests" / "manifest.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"
    assert (target_repo_root / "data" / "derived" / "eval_subsets" / "subset.txt").read_text(encoding="utf-8") == "subset"
    assert not (target_repo_root / "data" / "derived" / "float_manual_eval").exists()


def test_sync_dataset_repo_entry_script_exposes_zero_arg_main():
    import importlib.util

    script_path = Path("scripts/sync_dataset_repo.py")
    spec = importlib.util.spec_from_file_location("scripts_sync_dataset_repo", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert callable(module.main)
