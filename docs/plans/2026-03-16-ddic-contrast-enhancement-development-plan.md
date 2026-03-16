# DDIC Contrast Enhancement Development Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a DDIC-ready contrast enhancement algorithm and validation package for a pipeline that uses `Frame N` statistics and applies enhancement on `Frame N+1`.

**Architecture:** Start from a global histogram-to-LUT baseline that already matches the current repository and DDIC constraints, then run a structured branch comparison against one stronger low-cost improvement path. The workstream is organized as a closed loop: requirement freeze, test-plan construction, literature review, Python prototype, comprehensive validation, optimization, and hardware handoff preparation.

**Tech Stack:** Python 3.12, `pytest`, `numpy`, `Pillow`, Markdown reports, patent/paper review notes

---

## Chunk 1: Freeze Requirements And Success Criteria

### Task 1: Lock the hardware and image-quality envelope

**Files:**
- Review: `docs/plans/2026-03-06-ddic-contrast-enhancement-design.md`
- Review: `docs/research/2026-03-16-ddic-contrast-enhancement-research-notes.md`
- Modify: `docs/plans/2026-03-16-ddic-contrast-enhancement-development-plan.md`

- [ ] **Step 1: Freeze the non-negotiable DDIC constraints**
  - lock `input bit depth`, `target resolution`, `frame rate`, `histogram bin count`, `V blank` compute window, `LUT size`, and `allowed online operations`

- [ ] **Step 2: Freeze acceptance targets**
  - image-quality target: improve dark detail and global contrast without obvious highlight washout or skin-tone distortion
  - stability target: no visible frame flicker on slow content change and scene cuts
  - implementation target: online path remains `LUT-only` for the baseline branch

- [ ] **Step 3: Freeze the ranking rubric used later for method selection**
  - quality
  - temporal stability
  - hardware complexity
  - tuning difficulty
  - patent risk

### Task 2: Define measurable pass/fail metrics

**Files:**
- Create: `docs/reports/README.md`
- Create: `src/ddic_ce/metrics.py`
- Create: `tests/test_metrics.py`

- [ ] **Step 1: Write the failing tests for scalar metrics**
  - cover `mean`, `std`, `entropy`, `P2`, `P98`, `dynamic_range`, `dark_ratio`, `bright_ratio`

- [ ] **Step 2: Add contrast-specific metrics**
  - `AMBE`
  - `EME` or block contrast metric
  - monotonicity and full-range coverage checks on generated LUTs

- [ ] **Step 3: Add temporal metrics**
  - per-frame LUT delta
  - per-frame mean-luma delta
  - scene-cut response window

- [ ] **Step 4: Run tests**
  - Run: `PYTHONPATH=src pytest tests/test_metrics.py -v`
  - Expected: all metric tests pass

## Chunk 2: Build The Full Verification Plan And Automation Assets

### Task 3: Create synthetic pattern generators

**Files:**
- Create: `src/ddic_ce/patterns.py`
- Create: `tests/test_patterns.py`

- [ ] **Step 1: Write failing tests for pattern generation**
  - ramp
  - near-black ramp
  - near-white ramp
  - low-dynamic-range flat image
  - bimodal histogram image
  - tri-modal histogram image
  - checkerboard and edge-detail pattern
  - dark background with bright small object
  - bright background with dark small object
  - noise-on-dark pattern
  - skin-tone strip plus neutral background

- [ ] **Step 2: Implement deterministic pattern generators**
  - every pattern must have a stable seed and a saved metadata record

- [ ] **Step 3: Run tests**
  - Run: `PYTHONPATH=src pytest tests/test_patterns.py -v`
  - Expected: all pattern tests pass

### Task 4: Build dataset and sequence evaluation harness

**Files:**
- Modify: `src/ddic_ce/batch_runner.py`
- Create: `src/ddic_ce/temporal_runner.py`
- Create: `tests/test_temporal_runner.py`
- Create: `docs/research/dataset_manifest.md`

- [ ] **Step 1: Define dataset buckets**
  - synthetic patterns
  - natural still images
  - video or pseudo-video sequences for temporal stability
  - difficult corner cases: backlight scenes, low-light noise, faces, text UI, cartoon content

- [ ] **Step 2: Define dataset manifest fields**
  - source
  - license
  - scene tag
  - difficulty tag
  - expected failure modes

- [ ] **Step 3: Add a temporal runner**
  - input: ordered frames
  - output: per-frame histogram, LUT, metrics, and temporal deltas

- [ ] **Step 4: Run tests**
  - Run: `PYTHONPATH=src pytest tests/test_temporal_runner.py -v`
  - Expected: sequence-level processing is deterministic and metric export works

### Task 5: Convert the common pitfalls into explicit test cases

**Files:**
- Modify: `docs/research/dataset_manifest.md`
- Create: `docs/reports/pitfall_checklist.md`

- [ ] **Step 1: Encode the common failure modes**
  - highlight whitening
  - shadow noise boost
  - false contour amplification
  - gray-black lifting
  - overshoot on already high-contrast scenes
  - frame flicker on slow luminance drift
  - scene-cut instability
  - skin-tone unnaturalness
  - subtitle or UI halo emphasis

- [ ] **Step 2: Map each failure mode to patterns and real-image buckets**

- [ ] **Step 3: Add explicit pass/fail notes to the checklist**

## Chunk 3: Finish The Patent And Paper Review

### Task 6: Build the review ledger and implementation mapping

**Files:**
- Modify: `docs/research/2026-03-16-ddic-contrast-enhancement-research-notes.md`
- Create: `docs/research/patent_claim_mapping.md`

- [ ] **Step 1: For each candidate patent, record**
  - core method
  - scheduling model
  - memory model
  - whether it suggests a pure global path or a region-adaptive path

- [ ] **Step 2: For each candidate paper, record**
  - equation summary
  - tunable parameters
  - computational hot spots
  - likely DDIC simplifications

- [ ] **Step 3: Convert literature to three implementation branches**
  - `Path A`: global clip-limited histogram/CDF LUT
  - `Path B`: global LUT plus weighted histogram or adaptive gamma control
  - `Path C`: global LUT plus coarse region parameters

## Chunk 4: Prototype The Candidate Algorithms In Python

### Task 7: Harden the baseline branch

**Files:**
- Modify: `src/ddic_ce/reference_model.py`
- Modify: `tests/test_reference_model.py`

- [ ] **Step 1: Add configuration fields needed for controlled experiments**
  - clip limit policy
  - percentiles used for dark and bright ratios
  - temporal smoothing strength
  - optional highlight and shadow protection knobs

- [ ] **Step 2: Add failing tests for the new controls**

- [ ] **Step 3: Implement the minimal code to support those controls**

- [ ] **Step 4: Run tests**
  - Run: `PYTHONPATH=src pytest tests/test_reference_model.py -v`
  - Expected: baseline reference model remains monotonic and deterministic

### Task 8: Add the improvement branch

**Files:**
- Create: `src/ddic_ce/candidate_models.py`
- Create: `tests/test_candidate_models.py`

- [ ] **Step 1: Write failing tests for `Path B`**
  - weighted histogram or adaptive gamma branch must still emit a monotonic LUT
  - the online application model must remain `LUT-only`

- [ ] **Step 2: Implement `Path B` with the same output contract as the baseline**

- [ ] **Step 3: Run tests**
  - Run: `PYTHONPATH=src pytest tests/test_candidate_models.py -v`
  - Expected: both candidate branches expose the same processing interface

### Task 9: Keep the heavier spatial branch behind a gate

**Files:**
- Modify: `src/ddic_ce/candidate_models.py`
- Modify: `docs/research/2026-03-16-ddic-contrast-enhancement-research-notes.md`

- [ ] **Step 1: Add a stubbed `Path C` interface**
  - do not fully optimize it
  - only implement enough to estimate value versus complexity

- [ ] **Step 2: Record the extra state and memory this branch would require**

## Chunk 5: Down-Select The Best Method

### Task 10: Run the branch comparison and choose the primary algorithm

**Files:**
- Create: `src/ddic_ce/branch_evaluator.py`
- Create: `tests/test_branch_evaluator.py`
- Create: `docs/reports/branch_comparison.md`

- [ ] **Step 1: Write failing tests for branch-score aggregation**

- [ ] **Step 2: Implement score aggregation**
  - image quality
  - temporal stability
  - complexity
  - tuning difficulty

- [ ] **Step 3: Run the branch comparison on**
  - synthetic patterns
  - real still images
  - temporal sequences

- [ ] **Step 4: Write the decision**
  - choose one primary production path
  - keep one backup path
  - explicitly state why the rejected path lost

## Chunk 6: Execute The Comprehensive Test Plan

### Task 11: Produce the detailed validation report

**Files:**
- Create: `src/ddic_ce/reporting.py`
- Create: `docs/reports/validation_report_template.md`
- Create: `docs/reports/ddic_contrast_validation_round1.md`

- [ ] **Step 1: Export image-level artifacts**
  - enhanced image
  - histogram plot
  - LUT plot
  - per-image metric summary

- [ ] **Step 2: Export sequence-level artifacts**
  - frame-to-frame LUT delta
  - scene-cut behavior summary
  - temporal stability plots

- [ ] **Step 3: Write the report sections**
  - test setup
  - datasets and pattern inventory
  - major wins
  - failure cases
  - ablation summary
  - recommended parameter set

## Chunk 7: Optimize And Prepare For DDIC Handoff

### Task 12: Iterate on the selected method

**Files:**
- Modify: `src/ddic_ce/reference_model.py`
- Modify: `src/ddic_ce/candidate_models.py`
- Modify: `docs/reports/ddic_contrast_validation_round1.md`

- [ ] **Step 1: Prioritize issues from the first validation report**
  - temporal flicker
  - highlight protection
  - shadow noise control
  - over-enhancement on high-contrast scenes

- [ ] **Step 2: Apply one fix at a time and rerun the targeted subset**

- [ ] **Step 3: Promote only changes that improve the report without violating complexity limits**

### Task 13: Prepare the DDIC-facing delivery package

**Files:**
- Modify: `docs/plans/2026-03-06-ddic-contrast-enhancement-design.md`
- Create: `docs/reports/ddic_contrast_handoff_summary.md`

- [ ] **Step 1: Freeze the final algorithm contract**
  - statistics collected in `Frame N`
  - exact `V blank` operations
  - exact `Frame N+1` online path

- [ ] **Step 2: Add fixed-point and hardware notes**
  - quantization format
  - overflow policy
  - monotonic enforcement
  - memory estimate
  - cycle estimate

- [ ] **Step 3: Attach the final evidence package**
  - literature summary
  - branch-comparison report
  - validation report
  - selected parameter set
  - open risks

## Expected Execution Order
1. Freeze constraints and metrics.
2. Build the full verification and automation foundation.
3. Finish the literature review and map it to implementable branches.
4. Prototype `Path A`, then `Path B`, and keep `Path C` only as a gated comparison branch.
5. Run branch comparison, choose the production path, then issue the first full validation report.
6. Iterate only on measured failures and then freeze the DDIC handoff package.

## Provisional Recommendation
- Mandatory baseline: `Path A`, the current global histogram-to-LUT architecture.
- Main improvement branch: `Path B`, a stats-controlled weighted-histogram or adaptive-gamma LUT generator.
- Deferred branch: `Path C`, only if the measured quality gap remains significant after `Path B`.
