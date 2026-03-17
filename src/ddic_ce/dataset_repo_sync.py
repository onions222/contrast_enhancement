from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

DATASET_REPO_README = """# Contrast Dataset Repository

This repository stores image assets and curated manifests for the contrast-enhancement project.

## Contents
- `data/raw/`: original downloaded or generated image assets
- `data/derived/manifests/`: CSV and JSON manifests
- `data/derived/eval_subsets/`: curated subsets grouped by bucket

## Sync Source
These files are synced from the main contrast-enhancement code repository.

## What Is Not Stored Here
- transient evaluation outputs such as `data/derived/float_manual_eval/`
- Python caches or temporary files
"""

DATASET_REPO_GITIGNORE = """.DS_Store
__pycache__/
*.pyc
data/derived/float_manual_eval/
data/derived/resized/
"""


@dataclass(frozen=True)
class DatasetRepoSyncConfig:
    source_repo_root: Path = REPO_ROOT
    target_repo_root: Path = REPO_ROOT.parent / "contrast-dataset"


def _copy_tree_contents(source: Path, destination: Path) -> int:
    if not source.exists():
        return 0
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    return copied


def sync_dataset_repo(config: DatasetRepoSyncConfig | None = None) -> dict[str, object]:
    cfg = config or DatasetRepoSyncConfig()
    target_root = Path(cfg.target_repo_root)
    source_root = Path(cfg.source_repo_root)

    target_root.mkdir(parents=True, exist_ok=True)
    (target_root / "README.md").write_text(DATASET_REPO_README, encoding="utf-8")
    (target_root / ".gitignore").write_text(DATASET_REPO_GITIGNORE, encoding="utf-8")

    raw_files_copied = _copy_tree_contents(source_root / "data" / "raw", target_root / "data" / "raw")
    manifest_files_copied = _copy_tree_contents(
        source_root / "data" / "derived" / "manifests",
        target_root / "data" / "derived" / "manifests",
    )
    subset_files_copied = _copy_tree_contents(
        source_root / "data" / "derived" / "eval_subsets",
        target_root / "data" / "derived" / "eval_subsets",
    )

    return {
        "source_repo_root": str(source_root),
        "target_repo_root": str(target_root),
        "raw_files_copied": raw_files_copied,
        "manifest_files_copied": manifest_files_copied,
        "subset_files_copied": subset_files_copied,
    }


def main() -> dict[str, object]:
    summary = sync_dataset_repo()
    print(f"Dataset repo synced to: {summary['target_repo_root']}")
    print(f"Raw files copied: {summary['raw_files_copied']}")
    print(f"Manifest files copied: {summary['manifest_files_copied']}")
    print(f"Subset files copied: {summary['subset_files_copied']}")
    return summary


if __name__ == "__main__":
    main()
