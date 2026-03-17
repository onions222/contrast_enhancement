# Pattern Bypass Hardware-Friendly Criteria

## Scope
- Date: `2026-03-17`
- Goal: define a hardware-friendly `pattern bypass` rule set for the Python float contrast-enhancement pipeline, with the explicit constraint that the final DDIC-oriented version should avoid full-frame buffering.
- Target patterns:
  - gray ramp
  - RGB ramp
  - gray banded pattern
  - color bars
  - obvious synthetic pattern combinations
- Non-targets:
  - natural photographs with smooth sky/wall/fog gradients
  - ordinary low-texture photos
  - generic low-dynamic-range content that should still use the normal scene pipeline

## Problem Statement
The current Python-side pattern bypass can use full 2D plane structure, but that is not the right long-term contract for hardware. For hardware deployment, we need a rule set that:

- does not require a frame buffer
- can be computed online during raster scan
- preferably reuses already-available histogram statistics
- only adds low-cost streaming features and small control-state storage

The main design question is:

> Can pattern bypass be decided from histogram only?

Answer:

- `Histogram only` is useful as a coarse candidate filter.
- `Histogram only` is not sufficient to robustly separate synthetic pattern images from natural photographs.
- The recommended architecture is `histogram coarse filter + streaming structure confirmation`.

## Why Histogram Only Is Not Enough
Histogram preserves value distribution but discards spatial arrangement.

Examples of ambiguity:

- A perfect gray ramp and a randomly shuffled ramp can have nearly identical histograms.
- A synthetic banded pattern and a natural poster-like image can both show a small number of strong histogram peaks.
- A color-bar image and a different spatial arrangement of the same colors can produce the same per-channel histogram.

Therefore:

- histogram can say `this frame looks pattern-like`
- histogram alone cannot reliably say `this frame is a synthetic test pattern and should bypass`

## Recommended Decision Flow
Use a two-stage rule set.

### Stage 1: Histogram Candidate Filter
Use frame histogram and, for RGB input, per-channel histograms to identify a small set of pattern candidates.

This stage should be cheap and permissive:

- if not pattern-like, immediately return `pattern_bypass = 0`
- if pattern-like, continue to Stage 2

### Stage 2: Streaming Structure Confirmation
During scan, accumulate low-cost structural features using:

- previous pixel
- previous line buffer or line-level summary
- small counters/accumulators

This stage confirms whether the candidate is:

- a ramp
- a banded pattern
- color bars
- a clearly synthetic structured pattern

Only after Stage 2 should the system assert:

- `pattern_bypass = 1`
- identity LUT
- gain = `1.0`

## Stage-1 Histogram Features
These features are suitable for hardware control logic.

### 1. `active_bin_count`
Definition:

```text
active_bin_count = number of bins whose count > 0
```

Meaning:

- large for smooth/full-range ramps
- small for banded patterns and color bars

Use:

- high value can indicate `gray ramp candidate`
- low value can indicate `banded/color-bar candidate`

Limitation:

- natural gradients can also produce large `active_bin_count`
- some natural images also have sparse histograms

### 2. `max_bin_ratio`
Definition:

```text
max_bin_ratio = max(hist[i]) / total_pixel_count
```

Meaning:

- high for few-level patterns
- low for dense ramps

Use:

- helps distinguish dense ramps from sparse-level structured patterns

Limitation:

- still has no spatial information

### 3. `hist_uniformity_score`
Definition:

Use only active bins:

```text
mean_active = average count across active bins
hist_uniformity_score = average(|hist[i] - mean_active|) / mean_active
```

Meaning:

- low when counts across active bins are close to uniform
- gray ramps tend to be close to uniform

Use:

- strong support for `gray ramp candidate`

Limitation:

- some natural smooth gradients may also look uniform enough

### 4. `peak_bin_count`
Definition:

```text
peak_bin_count = number of bins whose count exceeds a fixed ratio threshold
```

Meaning:

- small number of strong peaks is common in banded patterns and color bars

Use:

- identify sparse structured candidates

Limitation:

- posters, UI screenshots, and some synthetic-looking real content may also trigger

### 5. `per_channel_active_bin_count`
Definition:

Apply `active_bin_count` independently to `R/G/B`.

Meaning:

- useful for RGB ramps and color bars
- for example, a single-channel ramp often shows:
  - one channel dense
  - two channels sparse or constant

Use:

- distinguish `RGB ramp candidate` from generic luma-only variation

Limitation:

- still cannot confirm spatial arrangement

## Stage-2 Streaming Features
These features do not require full-frame storage.

### 1. `row_repeat_count`
Requirement:

- one line buffer, or line hash/signature

Definition:

```text
row_repeat_count = number of rows that are identical or near-identical to the previous row
```

Meaning:

- horizontal ramp, vertical bars, color bars often repeat the same line many times

Use:

- strong evidence for synthetic structured pattern

Limitation:

- repeated rows alone do not distinguish ramp from bar pattern

### 2. `monotonic_row_ratio`
Definition:

For each row, count whether pixel sequence is monotonic non-decreasing or non-increasing.

```text
monotonic_row_ratio = monotonic_row_count / total_rows
```

Meaning:

- horizontal ramp usually has a very high monotonic row ratio

Use:

- confirm `gray ramp` and `RGB ramp`

Limitation:

- some synthetic but non-ramp patterns are not monotonic

### 3. `sign_flip_count`
Definition:

During each row scan, compute adjacent difference sign.

```text
sign_flip_count += 1 when sign(diff_t) != sign(diff_t-1) and both diffs are non-zero
```

Meaning:

- ramps have very few sign flips
- textured natural images have many sign flips

Use:

- reject natural textured gradients

Limitation:

- coarse banded patterns may also have low sign-flip counts

### 4. `plateau_run_score`
Definition:

Accumulate long same-value runs:

```text
plateau_run_score = total number of pixels belonging to runs longer than L
```

Meaning:

- color bars and banded patterns have long plateaus

Use:

- confirm `banded pattern` and `color bars`

Limitation:

- low-detail UI or graphics may also produce long runs

### 5. `transition_count_per_row`
Definition:

Count large adjacent jumps in each row:

```text
transition_count_per_row = number of |x_t - x_t-1| >= T
```

Meaning:

- color bars usually have a small, stable number of transitions
- natural content has more irregular transitions

Use:

- differentiate synthetic bars from photographs

Limitation:

- some structured UI content may still overlap

### 6. `boundary_alignment_score`
Requirement:

- line buffer or previous-line transition positions

Definition:

Track whether jump positions remain aligned across rows.

Meaning:

- color bars and vertical band patterns have highly aligned boundaries

Use:

- strong confirmation for `color bars` and vertical synthetic stripes

Limitation:

- requires slightly more control logic than simple counters

## Recommended Pattern Classes And Rules
Below are the recommended hardware-oriented rules.

### A. Gray Ramp
Stage-1 candidate:

- `active_bin_count` high
- `max_bin_ratio` low
- `hist_uniformity_score` low

Stage-2 confirm:

- `row_repeat_count` high or near-full
- `monotonic_row_ratio` high
- `sign_flip_count` low

Decision:

- `pattern_type = gray_ramp`
- `pattern_bypass = 1`

### B. RGB Ramp
Stage-1 candidate:

- one channel has high `active_bin_count`
- the other channels are nearly constant or sparse

Stage-2 confirm:

- high line repeat
- strong monotonicity along main scan direction
- low sign-flip count

Decision:

- `pattern_type = rgb_ramp`
- `pattern_bypass = 1`

### C. Gray Banded Pattern
Stage-1 candidate:

- `active_bin_count` low to medium
- `peak_bin_count` small
- `max_bin_ratio` high

Stage-2 confirm:

- high plateau score
- low, stable transition count
- repeated rows or repeated columns

Decision:

- `pattern_type = gray_banded`
- `pattern_bypass = 1`

### D. Color Bars
Stage-1 candidate:

- strong sparse peaks in `R/G/B`
- low to medium channel-wise active-bin counts

Stage-2 confirm:

- strong plateau score
- low transition count per row
- high boundary alignment score
- high row repeat

Decision:

- `pattern_type = color_bars`
- `pattern_bypass = 1`

### E. Pattern Combination
Definition:

- combinations of ramps, bars, banded blocks, and artificial structured regions

Recommendation:

- do not try to solve this with one weak heuristic
- require both:
  - Stage-1 pattern candidate
  - at least two independent Stage-2 confirmations

Decision:

- `pattern_type = pattern_combo`
- `pattern_bypass = 1`

## False-Positive Guard Rails
The system must avoid bypassing natural photographs.

Recommended guard rails:

- Do not bypass from histogram only.
- Require at least one spatial confirmation feature.
- Treat `smooth but textured` gradients as non-pattern:
  - if sign-flip count is high enough, reject bypass
- Treat `small-object two-tone frames` as non-pattern:
  - two-level content alone is not enough
- For color bars, require boundary alignment, not just sparse histograms.

## Hardware Cost Guidance
Approximate implementation cost by block:

### Lowest Cost
- global histogram
- `active_bin_count`
- `max_bin_ratio`
- `peak_bin_count`

### Low-to-Medium Cost
- previous-pixel difference logic
- sign-flip counter
- plateau-run counter
- transition counter

### Medium Cost But Still Hardware-Friendly
- one line buffer or line-signature buffer
- row-repeat comparison
- boundary-alignment comparison

### Not Recommended For First Version
- full-frame spatial analysis
- tile buffering
- morphology-like connected-component logic

## Recommended Bring-Up Order
Implement in this order:

1. gray ramp
2. gray banded pattern
3. RGB ramp
4. color bars
5. pattern combination

Reason:

- the first three are easier to express with simple counters and line-wise monotonic checks
- color bars need slightly richer spatial confirmation
- pattern combinations should be added last because their ambiguity is highest

## Python Simulation Guidance
The Python reference path should eventually simulate the hardware-oriented version using:

- histogram-derived candidate flags
- streaming-compatible structural features
- no dependence on full-frame 2D pattern templates

This is a different target from the current convenient software-only pattern detector. The software detector is useful for rapid validation, but the long-term hardware handoff should match the above feature set.

## Recommended Next Step
Next implementation step:

- replace the current software-convenient pattern bypass with a `hardware-friendly simulation mode`
- keep the rule split explicit:
  - `stage1_histogram_candidate`
  - `stage2_streaming_confirmation`
  - `pattern_bypass`

This allows direct comparison between:

- current convenient software detector
- future hardware-oriented detector

and reduces risk when the algorithm is handed off to MATLAB / RTL / DDIC implementation teams.
