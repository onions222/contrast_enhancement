# MATLAB HW Runtime Package Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete MATLAB hardware-runtime package under `matlab/` for the discrete-scene contrast enhancement algorithm, using basic MATLAB only and manual fixed-point semantics.

**Architecture:** Mirror the approved three-layer split from the conversion standard: `config` for constants and Q-format definitions, `control_update` for frame statistics and runtime LUT generation, and `datapath` for per-pixel gain lookup and RGB scaling. Add helper utilities, runnable scripts, validation, and a README so the package is self-contained and maps cleanly to DDIC-style control/data-path thinking.

**Tech Stack:** MATLAB `.m` scripts/functions, Python `pytest` asset tests, existing Python float golden under `src/ddic_ce_float`

---

## Chunk 1: Lock Package Shape

### Task 1: Add failing tests for MATLAB package assets

**Files:**
- Create: `tests/test_matlab_hw_runtime_assets.py`
- Create: `matlab/README.md`
- Create: `matlab/ce_hw_config.m`
- Create: `matlab/ce_hw_control_update.m`
- Create: `matlab/ce_hw_datapath.m`
- Create: `matlab/ce_hw_helpers.m`
- Create: `matlab/run_ce_hw_case.m`
- Create: `matlab/run_ce_hw_batch.m`
- Create: `matlab/validate_ce_hw_against_python.m`

- [ ] **Step 1: Write failing tests for required files and function signatures**
- [ ] **Step 2: Run `pytest tests/test_matlab_hw_runtime_assets.py -q` and confirm failure**
- [ ] **Step 3: Add the minimum MATLAB file skeletons and README**
- [ ] **Step 4: Run `pytest tests/test_matlab_hw_runtime_assets.py -q` and confirm pass**

## Chunk 2: Implement Runtime Logic

### Task 2: Implement config, helpers, control update, and datapath

**Files:**
- Modify: `matlab/ce_hw_config.m`
- Modify: `matlab/ce_hw_control_update.m`
- Modify: `matlab/ce_hw_datapath.m`
- Modify: `matlab/ce_hw_helpers.m`

- [ ] **Step 1: Add failing tests that inspect required constants and MATLAB API markers**
- [ ] **Step 2: Run focused tests and confirm failure**
- [ ] **Step 3: Implement the MATLAB fixed-point-style helpers and runtime logic**
- [ ] **Step 4: Re-run focused tests and confirm pass**

## Chunk 3: Add Runners And Validation

### Task 3: Implement run scripts and validation entrypoint

**Files:**
- Modify: `matlab/run_ce_hw_case.m`
- Modify: `matlab/run_ce_hw_batch.m`
- Modify: `matlab/validate_ce_hw_against_python.m`
- Modify: `tests/test_matlab_hw_runtime_assets.py`

- [ ] **Step 1: Extend tests to require runnable entrypoints and validation metrics names**
- [ ] **Step 2: Run focused tests and confirm failure**
- [ ] **Step 3: Implement case runner, batch runner, and validation script**
- [ ] **Step 4: Run focused tests and confirm pass**

## Chunk 4: Verify MATLAB Package

### Task 4: Run repository verification

**Files:**
- Verify only

- [ ] **Step 1: Run `PYTHONPATH=src pytest tests -q`**
- [ ] **Step 2: Run `/Applications/MATLAB_R2025a.app/bin/matlab -batch "addpath('matlab'); cfg=ce_hw_config(); disp(cfg.name);"`**
- [ ] **Step 3: Run `/Applications/MATLAB_R2025a.app/bin/matlab -batch "addpath('matlab'); s=run_ce_hw_case(); disp(s.scene_name);"`**
