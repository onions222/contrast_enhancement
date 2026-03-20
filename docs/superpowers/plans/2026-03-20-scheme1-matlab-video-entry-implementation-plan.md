# Scheme1 MATLAB Video Entry Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a MATLAB video entry for `scheme1` that reads a video file, processes frames in order with continuous temporal state propagation, and writes an enhanced output video under `outputs/scheme1`.

**Architecture:** Keep hardware-core logic unchanged. Add one video-frame wrapper and one video runner script. The runner owns `VideoReader`/`VideoWriter` and passes `runtime.state_out` from frame `t` to frame `t+1`.

**Tech Stack:** MATLAB, existing `scheme1/matlab` runtime, `VideoReader`, `VideoWriter`

---

## Chunk 1: Add Video Frame Wrapper

### Task 1: Create `ce1_hw_apply_to_video_frame.m`

**Files:**
- Create: `scheme1/matlab/ce1_hw_apply_to_video_frame.m`
- Reference: `scheme1/matlab/ce1_hw_apply_to_image.m`
- Reference: `scheme1/matlab/ce1_hw_control_update.m`
- Reference: `scheme1/matlab/ce1_hw_datapath.m`

- [ ] **Step 1: Copy the image-wrapper responsibility split**

Create a new MATLAB function that accepts:
- `frame_in`
- `cfg`
- `prev_state`

and returns a struct containing:
- `input_frame`
- `value_plane`
- `runtime`
- `datapath`
- `output_frame`
- `state_out`

- [ ] **Step 2: Implement grayscale path**

For 2-D input:
- treat input directly as `V`
- call `ce1_hw_control_update`
- call `ce1_hw_datapath`
- output `mapped_frame` as grayscale `uint8`

- [ ] **Step 3: Implement RGB path**

For RGB input:
- compute `V = max(R,G,B)`
- generate `runtime` and `datapath`
- compute gain map using:

```matlab
gain = double(V_out) ./ max(double(V_in), 1)
```

- multiply each RGB channel by `gain`
- clamp to `0..255`
- cast to `uint8`

- [ ] **Step 4: Return fixed output fields**

The function must always return `state_out = runtime.state_out`.

- [ ] **Step 5: Keep comments explicit**

Document:
- that this is not hardware core logic
- that temporal state is provided by the caller
- that the statistics domain is still HSV `V`

## Chunk 2: Add Video Runner

### Task 2: Create `run_ce1_hw_video.m`

**Files:**
- Create: `scheme1/matlab/run_ce1_hw_video.m`
- Reference: `scheme1/matlab/run_ce1_hw_image.m`

- [ ] **Step 1: Define fixed default paths**

At the top of the script define:
- `repo_root`
- `input_video_path`
- `output_root`
- `output_video_path`

Output must go under:
- `outputs/scheme1`

- [ ] **Step 2: Create config and initial state**

Initialize:

```matlab
cfg = ce1_hw_config();
prev_state = struct( ...
    'prev_lut_valid', uint8(0), ...
    'prev_lut', uint16(cfg.identity_lut(:)));
```

- [ ] **Step 3: Add video read/write setup**

Create:
- `reader = VideoReader(input_video_path);`
- `writer = VideoWriter(output_video_path, 'MPEG-4');`

Set:
- `writer.FrameRate = reader.FrameRate;`

- [ ] **Step 4: Add frame loop with continuous state**

Implement:

```matlab
while hasFrame(reader)
    frame_in = readFrame(reader);
    frame_result = ce1_hw_apply_to_video_frame(frame_in, cfg, prev_state);
    writeVideo(writer, frame_result.output_frame);
    prev_state = frame_result.state_out;
end
```

- [ ] **Step 5: Add summary output**

Print:
- input path
- output path
- frame count
- frame rate
- output size
- last-frame bypass reason if useful

## Chunk 3: Update README

### Task 3: Document video entry

**Files:**
- Modify: `scheme1/matlab/README.md`

- [ ] **Step 1: Add video entry section**

Document:
- `run_ce1_hw_video.m`
- default input/output path behavior
- that `prev_state` is propagated across the whole video

- [ ] **Step 2: Clarify differences from image/folder mode**

Explain:
- image/folder paths are per-image independent
- video path is temporal and frame-ordered

## Chunk 4: Verification

### Task 4: Run MATLAB video smoke test

**Files:**
- Run only

- [ ] **Step 1: Find a small local video sample**

Use an existing local video under the repo if available; otherwise create a temporary assumption path in the script and note it.

- [ ] **Step 2: Run the video script**

Run:

```bash
/Applications/MATLAB_R2025a.app/bin/matlab -batch "cd('/Users/onion/Desktop/code/Contrast'); addpath('scheme1/matlab'); run('scheme1/matlab/run_ce1_hw_video.m');"
```

Expected:
- output video created
- no runtime error

- [ ] **Step 3: Verify output file exists**

Check that:
- `outputs/scheme1/ce1_hw_video_output.mp4` exists

- [ ] **Step 4: Verify image runners still remain valid**

Run:

```bash
/Applications/MATLAB_R2025a.app/bin/matlab -batch "cd('/Users/onion/Desktop/code/Contrast'); addpath('scheme1/matlab'); run('scheme1/matlab/run_ce1_hw_image.m');"
```

Expected:
- still succeeds after video-entry changes

## Chunk 5: Commit

### Task 5: Save the change cleanly

**Files:**
- Add new MATLAB files
- Modify `scheme1/matlab/README.md`

- [ ] **Step 1: Stage files**

Run:

```bash
git add scheme1/matlab/ce1_hw_apply_to_video_frame.m \
        scheme1/matlab/run_ce1_hw_video.m \
        scheme1/matlab/README.md \
        docs/superpowers/specs/2026-03-20-scheme1-matlab-video-entry-design.md \
        docs/superpowers/plans/2026-03-20-scheme1-matlab-video-entry-implementation-plan.md
```

- [ ] **Step 2: Commit**

Run:

```bash
git commit -m "Add scheme1 MATLAB video entry"
```
