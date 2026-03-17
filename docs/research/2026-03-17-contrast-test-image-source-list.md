# Contrast Test Image Source List

## Goal
Move the project from fully synthetic reliability checks to a mixed evaluation set that contains real photographs and short temporal clips. The target is not "as many images as possible". The target is a compact set that stresses the known failure modes of contrast enhancement:
- highlight washout
- shadow crush
- noise amplification
- banding on smooth gradients
- halo on text and edges
- skin-tone shift
- temporal flicker

## Priority order
1. Low-light real photos
2. High-key bright photos
3. Text / sign / subtitle-like content
4. Faces and skin tones
5. Smooth gradients and already-contrasty scenes
6. Temporal clips captured on phone

## Recommended sources
### 1. MIT-Adobe FiveK
- Link: [MIT-Adobe FiveK](https://data.csail.mit.edu/graphics/fivek/)
- Why it matters:
  - broad scene diversity
  - semantic metadata helps filter people, nature, indoor, outdoor, time of day
  - good source for high-key, normal, backlit, and face/skin samples
- Use it for:
  - high-key daylight
  - normal mixed-light stills
  - people / skin-tone stills
- Do not use it alone for:
  - extreme low-light noise
  - subtitle / text overlays

### 2. BSDS500
- Link: [BSDS500](https://www2.eecs.berkeley.edu/Research/Projects/CS/vision/grouping/resources.html)
- Why it matters:
  - natural images with rich boundaries and textures
  - useful for checking whether enhancement over-pushes already-contrasty scenes
- Use it for:
  - foliage, textures, thin edges, shadow boundaries
  - already high-contrast content
- Do not use it alone for:
  - very dark scenes
  - noise amplification

### 3. ExDark
- Link: [ExDark official repository](https://github.com/cs-chan/Exclusively-Dark-Image-Dataset)
- Why it matters:
  - large real low-light collection
  - multiple illumination conditions from very dark to twilight
  - good for noise, small bright objects, dark background scenes
- Use it for:
  - street night scenes
  - dim indoor scenes
  - signboards and bright objects on dark backgrounds
- Watch out:
  - commercial-use permission is separate

### 4. SID
- Link: [SID official page](https://cchen156.github.io/SID.html)
- Why it matters:
  - extreme low-light paired data
  - useful for studying brighten-vs-noise tradeoffs under very poor illumination
- Use it for:
  - dark noisy scenes
  - identifying when enhancement reveals detail versus only lifts noise
- Do not use it alone for:
  - ordinary consumer-photo quality judgment, because it is more extreme than many typical scenes

### 5. Text in the Dark
- Link: [Text in the Dark](https://github.com/chunchet-ng/Text-in-the-Dark)
- Why it matters:
  - directly useful for text edges, subtitle-like halos, sign clarity, edge shimmer
- Use it for:
  - subtitles / UI / text-like scenes
  - halo and flicker checks on hard bright-dark boundaries

### 6. USC-SIPI
- Link: [USC-SIPI Image Database](https://sipi.usc.edu/database/)
- Why it matters:
  - classic processing images and some short sequences
  - useful for gradients, textures, and familiar artifact-spotting content
- Use it for:
  - smooth gradient and banding checks
  - sequence-based sanity checks
- Watch out:
  - copyright status varies; keep local only unless usage is clearly allowed

## What to collect first
If you want a practical first batch, collect these before anything else:

| type | count | source |
| --- | --- | --- |
| Low-light noisy photos | 12 | `ExDark`, `SID` |
| High-key bright photos | 8 | `MIT-Adobe FiveK`, `BSDS500` |
| Faces / skin-tone photos | 6 | `MIT-Adobe FiveK`, self-capture |
| Text / sign / subtitle-like photos | 6 | `Text in the Dark`, self-capture |
| Smooth-gradient / wall / sky photos | 4 | `USC-SIPI`, self-capture |
| Already high-contrast photos | 4 | `BSDS500`, `MIT-Adobe FiveK` |

Recommended first batch size: 40 still images.

## What to capture yourself
Public datasets do not cover everything this project needs. Capture these on a phone:
- dark room with a bright lamp or monitor
- subtitles on a dark movie frame
- phone settings UI at low brightness
- face near a window and face under warm dim light
- hallway or parking lot with bright sign and dark background
- slow pan from dark to bright to trigger auto-exposure

Self-capture is the most direct way to get realistic temporal clips and subtitle/UI content.

## Storage rules
- Keep originals under `data/raw/`.
- Put resized or reformatted copies under `data/derived/`.
- Do not commit raw datasets into Git.
- For every selected file, tag:
  - `scene_tag`
  - `difficulty_tag`
  - `expected_failure_modes`

## Next action
The most efficient next step is:
1. Collect 40 still images using the first-batch table above.
2. Collect 8 to 12 short phone clips for temporal testing.
3. Record every file in [dataset_manifest.md](/Users/onion/Desktop/code/Contrast/docs/research/dataset_manifest.md).
4. Only then build the batch runner over real-image buckets.
