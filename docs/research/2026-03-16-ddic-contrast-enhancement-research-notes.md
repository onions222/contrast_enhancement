# DDIC Contrast Enhancement First-Round Research Notes

## Scope
- Date: `2026-03-16`
- Goal: collect first-round patents and papers that are useful for a DDIC contrast enhancement pipeline with `Frame N statistics -> V blank compute -> Frame N+1 apply`
- Provisional hardware assumption:
  - online pixel path should stay close to `1x LUT + clamp`
  - prefer global statistics first
  - avoid tile/local buffering unless later resource review says it is acceptable

## Initial Screening Conclusion
- Highest-confidence baseline: `clip-limited histogram -> CDF -> monotonic LUT`, with frame-to-frame LUT smoothing.
- Most promising low-cost upgrade: add `weighted histogram` or `adaptive gamma` control using frame statistics, but keep the online path LUT-only.
- Reserve path, not default path: coarse region-adaptive enhancement with a small number of region parameters. This has value, but hardware scheduling and storage risk are materially higher.

## Patent Candidates

### 1. US6259472B1 - Contrast enhancement system and method for digital imaging
- Relevance:
  - classic histogram-based contrast remapping prior art
  - useful as a baseline reference for global histogram/CDF-style mapping logic
- DDIC fit: medium
  - method family is relevant
  - hardware scheduling details are limited compared with display-specific patents
- Local material:
  - PDF: `docs/research/materials/patents/US6259472B1.pdf`
- Source:
  - `https://patents.google.com/patent/US6259472B1/en`

### 2. US7760961B2 - Image display device and method of controlling the same
- Relevance:
  - histogram binning, lookup-table generation, and display-side control flow
  - explicitly useful for `blanking interval` compute and `single SRAM` reuse thinking
- DDIC fit: high
  - close to actual display pipeline constraints
  - strong reference for a low-complexity `N/N+1` scheduling pattern
- Local material:
  - PDF: `docs/research/materials/patents/US7760961B2.pdf`
- Source:
  - `https://patents.google.com/patent/US7760961B2/en`

### 3. CN114267130A - Display image contrast enhancement method, device, apparatus, chip and storage medium
- Relevance:
  - explicitly discusses histogram accumulation, blanking-interval LUT generation, and storage reuse
  - contains hardware-oriented structure that is close to DDIC implementation thinking
- DDIC fit: high
  - not a US patent, but technically very relevant to the target pipeline
- Local material:
  - HTML entry page: `docs/research/materials/patents/CN114267130A.html`
  - direct PDF fetch failed because the public storage endpoint returned access denial:
    `docs/research/materials/patents/CN114267130A.access_denied.xml`
- Source:
  - `https://patents.google.com/patent/CN114267130A/en`

### 4. US12182979B2 - System and method for region-adaptive contrast enhancement of video
- Relevance:
  - useful if the project later moves from pure global mapping to coarse region-adaptive control
  - likely helpful for defining a future `global LUT + region gain/bias` fallback path
- DDIC fit: medium
  - conceptually useful
  - may be too heavy for the first tape-out-style implementation
- Local material:
  - HTML entry page: `docs/research/materials/patents/US12182979B2.html`
  - direct PDF fetch failed because the public storage endpoint returned access denial:
    `docs/research/materials/patents/US12182979B2.access_denied.xml`
- Source:
  - `https://patents.google.com/patent/US12182979B2/en`

### 5. US9747615B2 - System and method for automatic content enhancement of video streams
- Relevance:
  - useful for control logic, scene adaptation, and temporal stability ideas
  - more relevant to parameter policy than to the core low-cost mapping primitive
- DDIC fit: medium
  - better as an inspiration source for control heuristics than as the baseline algorithm
- Local material:
  - HTML entry page: `docs/research/materials/patents/US9747615B2.html`
  - direct PDF fetch failed because the public storage endpoint returned access denial:
    `docs/research/materials/patents/US9747615B2.access_denied.xml`
- Source:
  - `https://patents.google.com/patent/US9747615B2/en`

## Paper Candidates

### 1. Efficient Contrast Enhancement Using Adaptive Gamma Correction With Weighting Distribution
- Venue: `IEEE Transactions on Image Processing`, 2009
- Relevance:
  - low-complexity global method
  - strong candidate for a `stats -> gamma policy -> LUT` branch
  - useful when pure histogram equalization is too aggressive or unstable
- DDIC fit: high
  - the online path can still remain LUT-only after offline or blanking-time curve generation
- Local material:
  - HTML abstract page: `docs/research/materials/papers/Adaptive_Gamma_Correction_With_Weighting_Distribution_IEEE_2009.html`
- Source:
  - `https://ieeexplore.ieee.org/document/5290381`

### 2. Efficient Brightness Preserving Dynamic Range Histogram Equalization
- Venue: `EURASIP Journal on Image and Video Processing`, 2014
- Relevance:
  - useful for building brightness-preserving guard rails around histogram equalization
  - helpful for avoiding common failures such as mean shift, washed highlights, and dark-region overboost
- DDIC fit: medium to high
  - direct full method may be heavier than the baseline
  - but the split/limit/protect ideas are useful for the DDIC tuning policy
- Local material:
  - PDF: `docs/research/materials/papers/BPWDRHE_2014_10.1186-1687-5281-2014-44.pdf`
- Source:
  - `https://jivp-eurasipjournals.springeropen.com/articles/10.1186/1687-5281-2014-44`

## Recommended Method Paths After Round 1

### Path A - Global clip-limited CDF LUT
- Definition:
  - `Frame N` accumulates a global HSV `V` histogram
  - `V blank` performs smoothing, clip-and-redistribute, CDF build, LUT expansion, monotonic clamp, and temporal IIR
  - `Frame N+1` applies a single LUT
- Why keep it:
  - best fit for DDIC implementation constraints
  - already aligned with the current repo's `scheme3/src/ce_scheme3/reference_model.py`
- Risk:
  - purely global mapping may not handle mixed dark/bright content well

### Path B - Global LUT plus adaptive gamma or weighted histogram control
- Definition:
  - keep the same global statistics collection
  - use frame stats such as `mean`, `dark ratio`, `bright ratio`, `P98-P2` to modulate histogram weighting or gamma
  - still emit only one monotonic LUT for `Frame N+1`
- Why keep it:
  - likely the best upgrade path if Path A is too flat or too aggressive
  - does not break the low-cost online path
- Risk:
  - more tuning knobs
  - higher risk of frame-to-frame instability if temporal smoothing is weak

### Path C - Global LUT plus coarse region-adaptive parameters
- Definition:
  - keep one global LUT
  - add a small number of coarse spatial parameters, for example region gain or base level
- Why keep it:
  - useful if the target quality gap after Path B is still too large
- Risk:
  - more memory and scheduling complexity
  - much easier to drift outside current DDIC resource assumptions

## Round-1 Recommendation
- Primary execution order:
  1. Path A as the mandatory baseline
  2. Path B as the main improvement branch
  3. Path C only if A/B cannot close the quality gap
- Provisional preferred direction:
  - keep `Path A` as the initial deliverable
  - prepare `Path B` as the most realistic optimization branch

## Gaps To Close In Round 2
- Confirm the actual hardware budget:
  - histogram bin count
  - available `V blank` cycles
  - allowed multiplier count
  - whether any coarse region statistics are acceptable
- Expand the paper list with:
  - one stronger brightness-preservation paper
  - one stronger temporal-stability or video-enhancement paper
- Perform a claim-to-implementation mapping pass on the patents before freezing the final production path.
