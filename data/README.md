# Local Data Layout

This project should keep downloaded test images outside versioned source files.

Recommended layout:

```text
data/
  README.md
  raw/
    mit_adobe_fivek/
    bsds500/
    exdark/
    sid/
    text_in_the_dark/
    usc_sipi/
    self_capture/
  derived/
    manifests/
    resized/
    eval_subsets/
    float_manual_eval/
```

Rules:
- `data/raw/` and `data/derived/` are ignored by Git.
- Downloaded real images and generated synthetic images are local assets only and should not be pushed to the remote repository.
- Keep original files under `data/raw/`.
- Put any resized or converted files under `data/derived/`.
- Record chosen files and tags in [dataset_manifest.md](/Users/onion/Desktop/code/Contrast/docs/research/dataset_manifest.md).
- You can generate the synthetic starter set with one command:

```bash
python scripts/build_starter_test_dataset.py
```

- This command writes:
  - raw synthetic images to `data/raw/starter_synth_v1/`
  - the synthetic manifest to `data/derived/manifests/2026-03-17-starter_synth_v1_manifest.csv`
  - the eval subset to `data/derived/eval_subsets/starter_synth_v1/`
- The synthetic set now includes:
  - the original starter scenes
  - `rgb_ramp_*` single-channel ramps for `R/G/B`
  - `gray_ramp_*` grayscale ramps
  - `color_bars_*` RGB/gray/skin/color-bar patterns
- If you prefer the repository-root entry point, [build_starter_test_dataset.py](/Users/onion/Desktop/code/Contrast/build_starter_test_dataset.py) remains available and calls the same generator.
- You can build a public first-batch subset from local dataset folders by running [build_public_eval_subset.py](/Users/onion/Desktop/code/Contrast/build_public_eval_subset.py).
- If you want a separate dataset repository so image assets are not mixed into the main code repository, you can sync one with:

```bash
python scripts/sync_dataset_repo.py
```

- By default this creates or updates a sibling folder `../contrast-dataset/` and copies:
  - `data/raw/`
  - `data/derived/manifests/`
  - `data/derived/eval_subsets/`
- It does not copy transient evaluation outputs such as `data/derived/float_manual_eval/`.
