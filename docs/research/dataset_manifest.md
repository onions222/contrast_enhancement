# DDIC Contrast Dataset Manifest

## Buckets
- Synthetic patterns
- Natural still images
- Temporal sequences
- Corner cases

## Required fields
- dataset_id
- source
- license
- source_url
- local_root
- scene_tag
- difficulty_tag
- expected_failure_modes
- split
- selected_count
- notes

## Initial coverage targets
- backlight scenes
- low-light noisy scenes
- face and skin-tone scenes
- UI or subtitle overlays
- cartoon or synthetic graphics
- already high-contrast scenes

## Recommended external sources
| dataset_id | source | source_url | license | Why collect it |
| --- | --- | --- | --- | --- |
| `mit_adobe_fivek` | MIT CSAIL | [MIT-Adobe FiveK](https://data.csail.mit.edu/graphics/fivek/) | Research licenses listed on source page | Broad natural-photo coverage with semantic metadata such as people, lighting, indoor/outdoor |
| `bsds500` | UC Berkeley | [BSDS500](https://www2.eecs.berkeley.edu/Research/Projects/CS/vision/grouping/resources.html) | Benchmark/research dataset terms on source site | Natural edges, textures, foliage, already-contrasty scenes |
| `exdark` | Universiti Malaya authors | [ExDark official repository](https://github.com/cs-chan/Exclusively-Dark-Image-Dataset) | BSD-3-Clause for project; commercial use contact required | Real low-light scenes across 10 illumination conditions |
| `sid` | Chen Chen et al. | [SID official page](https://cchen156.github.io/SID.html) | Dataset terms on source page | Extreme low-light paired data; useful for brightening vs. noise tradeoff |
| `text_in_the_dark` | Official paper repository | [Text in the Dark](https://github.com/chunchet-ng/Text-in-the-Dark) | See repository / dataset terms | Low-light text and overlay-like content; useful for subtitles, UI, sign edges |
| `usc_sipi` | USC SIPI | [USC-SIPI Image Database](https://sipi.usc.edu/database/) | Research use; many images have unclear copyright | Classic gradients, textures, faces, and short sequences for artifact checks |

## Starter collection target
Collect a small but useful first batch before touching large full datasets.

| bucket | recommended_source | target_count | selection rule |
| --- | --- | --- | --- |
| High-key / bright outdoor | `mit_adobe_fivek`, `bsds500` | 8 | bright sky, snow, beach, white walls, backlit daylight |
| Normal natural photos | `mit_adobe_fivek`, `bsds500` | 8 | medium dynamic range, mixed objects, foliage, indoor daylight |
| Low-key / dark scenes | `exdark`, `sid` | 12 | indoor dim, street night, twilight, shop signs, parking lots |
| Low-light with visible noise | `sid`, `exdark` | 8 | very dark frames with obvious sensor noise or low SNR |
| Faces / skin tones | `mit_adobe_fivek`, self-captured | 6 | faces in mixed light, warm indoor light, dark skin / light skin variation |
| Text / UI / subtitle-like | `text_in_the_dark`, self-captured | 6 | bright text on dark background, signboards, subtitle overlays, menu UI |
| Fine gradients / smooth ramps | `usc_sipi`, self-generated captures | 4 | sky gradients, walls, shadows, smooth illumination |
| Already high-contrast scenes | `bsds500`, `mit_adobe_fivek` | 4 | hard sunlight, black-white subjects, deep shadows with highlights |

Suggested first-round total: 56 still images.

## Temporal sequence target
Still images are not enough for this project. Collect short sequences separately.

| bucket | source | target_count | notes |
| --- | --- | --- | --- |
| Slow exposure drift | self-captured smartphone clips | 4 sequences | walk from dim to bright or auto-exposure settling |
| Sudden scene cut | self-captured clips | 4 sequences | cut from indoor dark to outdoor bright and back |
| Low-light handheld noise | self-captured clips, `usc_sipi` sequences | 4 sequences | flicker and noise stability |
| Text / sign motion | `text_in_the_dark`, self-captured clips | 2 sequences | test halo and temporal shimmer on edges |

## Recommended local layout
Do not commit raw datasets into Git. Store them under ignored directories.

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
```

## Manifest row template
For every selected image or sequence, record one row with these fields:

```text
dataset_id,source,source_url,license,local_root,split,selected_count,scene_tag,difficulty_tag,expected_failure_modes,notes
```

Example:

```text
exdark,ExDark,https://github.com/cs-chan/Exclusively-Dark-Image-Dataset,BSD-3-Clause,data/raw/exdark,test,1,low_light_night|bright_sign,noise|small_bright_object,noise_boost|bypass_miss|halo,street scene with bright shop sign
```

## Selection rules
- Prefer images with clear failure-mode value over large random dumps.
- Keep at least one manually curated tag for every image.
- Keep raw originals and do any resizing or format conversion under `data/derived/`.
- For datasets with uncertain or restrictive copyright, keep them local and do not redistribute them from this repository.
- For UI/subtitle-like content, self-captured screenshots or phone recordings are recommended because public datasets are limited.
