# Pattern Bypass Hardware-Friendly Criteria

## Scope
- Date: `2026-03-17`
- Goal: define a hardware-friendly `pattern bypass` baseline for the Python float contrast-enhancement pipeline.
- Final deployment target: DDIC-oriented hardware path with tight resource limits.
- Hard constraints:
  - no frame buffer
  - no line-buffer-dependent stage-2 structure analysis
  - histogram-driven decision only
- Target patterns:
  - gray ramp
  - RGB ramp projected to luma
  - gray banded pattern
  - color bars
  - comb / sawtooth / alternating-hole synthetic patterns
- Strategy:
  - prefer high recall on synthetic test patterns
  - it is acceptable to bypass some suspicious non-natural images if this helps catch more test patterns

## Final Design Decision
This document supersedes the earlier `histogram + streaming confirmation` direction.

The baseline rule set is now:

- input: `32-bin luma histogram`
- output: `pattern_bypass_flag`
- decision style: pure histogram classification

The reason for this change is hardware cost:

- `32-bin histogram` is materially cheaper than 256-bin control statistics
- streaming row/column confirmation still adds structural logic cost that is not justified for the current priority
- the current priority is to aggressively intercept synthetic test patterns, especially gradient-like inputs

## Problem Framing
The pattern-bypass problem is no longer framed as:

> "Can we robustly separate synthetic patterns from all natural photographs?"

It is now framed as:

> "Can we use a low-cost histogram-only rule set to catch as many pattern-like test images as possible?"

This is an intentionally more aggressive objective.

## Histogram Representation
Use a fixed `32-bin` luma histogram.

For 8-bit luma:

```text
bin_index = floor(luma / 8)
```

This is the recommended first implementation target.

If later validation shows insufficient separation, the fallback upgrade path is:

- keep the same rule structure
- replace `32-bin` with `64-bin`

## Core Features
The final baseline uses only histogram-domain features.

### 1. `active_bin_count`
Definition:

```text
active_bin_count = number of bins with hist[i] > 0
```

Meaning:

- large for dense gradient-like content
- small for sparse banded / color-bar-like content

### 2. `first_active_bin`
Definition:

```text
first_active_bin = smallest i such that hist[i] > 0
```

### 3. `last_active_bin`
Definition:

```text
last_active_bin = largest i such that hist[i] > 0
```

### 4. `span_bin_count`
Definition:

```text
span_bin_count = last_active_bin - first_active_bin + 1
```

Meaning:

- wide for full or near-full ramps
- can also be wide for comb-like patterns

### 5. `active_run_count`
Definition:

Count the number of non-zero contiguous segments.

Examples:

- `1111111000` -> `1`
- `1100110011` -> `3`

Meaning:

- small for continuous ramps
- large for fragmented or comb-like patterns

### 6. `longest_active_run`
Definition:

```text
longest_active_run = maximum contiguous active-bin segment length
```

Meaning:

- large for dense gradients
- smaller for fragmented sparse/comb patterns

### 7. `hole_count`
Definition:

```text
hole_count = span_bin_count - active_bin_count
```

Meaning:

- near zero for continuous ramps
- large for alternating-hole or fragmented patterns

### 8. `sum_abs_diff`
Definition:

```text
sum_abs_diff = sum(|hist[i+1] - hist[i]|) over i = 0 .. bin_count-2
```

Meaning:

- small for flat, smooth histogram shapes
- large for jagged, comb, or strongly peaked distributions

This is the hardware-oriented form of the earlier "pdf smoothness / flatness" idea.

### 9. `max_bin_count`
Definition:

```text
max_bin_count = max(hist[i])
```

Meaning:

- large for sparse pattern classes such as color bars or few-level banded patterns

## Pattern Classes
The final classification is split into three classes.

### A. `dense_gradient_pattern`
Target coverage:

- gray ramp
- RGB ramp projected to luma
- continuous gradient test images

Histogram shape:

- many active bins
- wide active span
- very few runs
- few or no holes
- relatively smooth / flat histogram

### B. `sparse_pattern`
Target coverage:

- color bars
- few-level gray banded patterns
- sparse synthetic level-test patterns

Histogram shape:

- small active-bin count
- often a few dominant peaks
- usually simple run structure

### C. `comb_sawtooth_pattern`
Target coverage:

- alternating active/zero-bin distributions
- comb-shaped histograms
- sawtooth / missing-level synthetic patterns

Example:

```text
(0,200), (1,0), (2,200), (3,0), (4,200), ...
```

Histogram shape:

- span can be wide
- many holes inside the span
- many short runs
- strong adjacent-bin fluctuations

## Final Decision Logic
The final output rule is:

```text
pattern_bypass_flag =
    dense_gradient_pattern
    OR sparse_pattern
    OR comb_sawtooth_pattern
```

This logic is intentionally recall-oriented.

## First-Pass Decision Skeleton
The first-pass baseline should avoid overcomplicating the control path.

### `dense_gradient_pattern`

```text
active_bin_count >= T_dense_active
AND span_bin_count >= T_dense_span
AND active_run_count <= T_dense_runs
AND hole_count <= T_dense_holes
```

### `sparse_pattern`

```text
active_bin_count <= T_sparse_active
```

### `comb_sawtooth_pattern`

```text
span_bin_count >= T_comb_span
AND hole_count * K_comb_hole >= span_bin_count
AND active_run_count >= T_comb_runs
```

This is the first-pass rule skeleton.

## Second-Pass Tightening Features
After the first pass catches the major test-pattern classes, the following constraints can be added to tighten the boundary.

### `dense_gradient_pattern` tightening

```text
sum_abs_diff <= K_dense_flat * mean_active_ref
```

Interpretation:

- the histogram should remain relatively flat and smooth

### `sparse_pattern` tightening

```text
max_bin_count * K_sparse_peak >= total_pixel_count
```

Interpretation:

- at least one histogram peak should be sufficiently dominant

### `comb_sawtooth_pattern` tightening

```text
sum_abs_diff >= K_comb_flat * mean_active_ref
```

Interpretation:

- adjacent-bin fluctuation should be clearly strong

## Threshold Search Guidance
Thresholds should be searched in stages rather than all at once.

### Stage 1: Coarse structural separation
Search first:

- `T_dense_active`
- `T_dense_span`
- `T_dense_runs`
- `T_dense_holes`
- `T_sparse_active`
- `T_comb_span`
- `K_comb_hole`
- `T_comb_runs`

Goal:

- separate dense gradients, sparse patterns, and comb patterns with simple structural signals

### Stage 2: Boundary tightening
Then search:

- `K_dense_flat`
- `K_sparse_peak`
- `K_comb_flat`

Goal:

- tighten false positives only after target-pattern recall is already high

## Recommended Search Ranges
These are search ranges, not final values.

### Dense-gradient parameters
- `T_dense_active`: `14 ~ 24`
- `T_dense_span`: `16 ~ 28`
- `T_dense_runs`: `1 ~ 3`
- `T_dense_holes`: `0 ~ 4`

### Sparse-pattern parameters
- `T_sparse_active`: `2 ~ 8`

### Comb-pattern parameters
- `T_comb_span`: `10 ~ 24`
- `T_comb_runs`: `4 ~ 12`

The multiplier-style constants should be searched as small discrete bands rather than continuous values:

- `K_dense_flat`: strict / medium / relaxed
- `K_sparse_peak`: medium / high / very_high
- `K_comb_hole`: medium / high / very_high
- `K_comb_flat`: medium / high / very_high

## Integer-Only Implementation Rule
The hardware-oriented rule set should avoid floating-point and avoid real division.

All ratio-style comparisons should be converted into cross-multiplication form.

Examples:

Instead of:

```text
hole_count / span_bin_count >= a / b
```

use:

```text
hole_count * b >= span_bin_count * a
```

Instead of:

```text
sum_abs_diff / mean_active_ref <= c
```

use an equivalent integer comparison based on:

```text
sum_abs_diff <= c * mean_active_ref
```

## Tuning Priority
The validation priority should follow this order:

1. make `dense_gradient_pattern` high recall
2. make `comb_sawtooth_pattern` high recall
3. add `sparse_pattern`
4. only then tighten with flatness / peak constraints

Reason:

- the most explicit current weakness is gradient/pattern handling
- dense and comb cases should be solved first
- sparse-pattern refinement can follow

## Validation Buckets
Evaluation should be bucketed by intent rather than only reporting global averages.

Recommended buckets:

- `dense_gradient_target`
- `sparse_pattern_target`
- `comb_target`
- `non_target_reference`

Primary metrics:

- target interception rate
- non-target over-bypass rate

Because the current project priority is high recall on synthetic patterns, optimization should prefer raising interception rate first.

## Final Baseline Summary
The agreed baseline is:

- use `32-bin luma histogram`
- use histogram-only pattern bypass
- classify into:
  - `dense_gradient_pattern`
  - `sparse_pattern`
  - `comb_sawtooth_pattern`
- assert:

```text
pattern_bypass_flag =
    dense_gradient_pattern
    OR sparse_pattern
    OR comb_sawtooth_pattern
```

- tune thresholds in two stages:
  - first structural thresholds
  - then flatness / peak tightening

This document is the baseline contract for the next implementation step.
