from pathlib import Path


def test_matlab_hw_runtime_package_files_exist():
    root = Path(__file__).resolve().parents[1]
    matlab_dir = root / "matlab"

    required = [
        "README.md",
        "ce_hw_runtime_design.md",
        "ce_hw_config.m",
        "ce_hw_control_update.m",
        "ce_hw_datapath.m",
        "ce_hw_helpers.m",
        "run_ce_hw_case.m",
        "run_ce_hw_batch.m",
        "validate_ce_hw_against_python.m",
    ]

    assert matlab_dir.is_dir()
    for name in required:
        assert (matlab_dir / name).is_file(), name


def test_matlab_hw_runtime_entrypoints_match_script_and_function_roles():
    root = Path(__file__).resolve().parents[1]
    matlab_dir = root / "matlab"

    function_expectations = {
        "ce_hw_config.m": "function cfg = ce_hw_config(",
        "ce_hw_control_update.m": "function runtime = ce_hw_control_update(",
        "ce_hw_datapath.m": "function out = ce_hw_datapath(",
        "ce_hw_helpers.m": "function varargout = ce_hw_helpers(",
        "validate_ce_hw_against_python.m": "function report = validate_ce_hw_against_python(",
    }

    for name, marker in function_expectations.items():
        content = (matlab_dir / name).read_text(encoding="utf-8")
        assert marker in content

    case_script = (matlab_dir / "run_ce_hw_case.m").read_text(encoding="utf-8")
    batch_script = (matlab_dir / "run_ce_hw_batch.m").read_text(encoding="utf-8")

    assert not case_script.lstrip().startswith("function ")
    assert not batch_script.lstrip().startswith("function ")
    assert "result = struct();" in case_script
    assert "summary = struct();" in batch_script
    assert "if ~exist('input_frame', 'var') || isempty(input_frame)" in case_script
    assert "if ~exist('cases', 'var') || isempty(cases)" in batch_script


def test_matlab_hw_runtime_docs_and_validation_markers_exist():
    root = Path(__file__).resolve().parents[1]
    matlab_dir = root / "matlab"

    readme = (matlab_dir / "README.md").read_text(encoding="utf-8")
    design_doc = (matlab_dir / "ce_hw_runtime_design.md").read_text(encoding="utf-8")
    validate = (matlab_dir / "validate_ce_hw_against_python.m").read_text(encoding="utf-8")

    assert "Offline / Control / Datapath" in readme
    assert "MATLAB 硬件运行时" in readme
    assert "文件职责" in readme
    assert "典型用法" in readme
    assert "run('run_ce_hw_case.m')" in readme
    assert "run('run_ce_hw_batch.m')" in readme
    assert "## 1. 问题定义与 I/O 契约" in design_doc
    assert "## 4. 浮点版本算法说明" in design_doc
    assert "## 5. 硬件版本算法说明" in design_doc
    assert "## 7. 定点实现策略" in design_doc
    assert "## 8. 硬件资源估算" in design_doc
    assert "## 10. 详细流程图" in design_doc
    assert "## 11. 验证计划与验收标准" in design_doc
    assert "关键数据格式" in design_doc
    assert "模块划分建议" in design_doc
    assert "scene-cut" in design_doc
    assert "scene_id" in design_doc
    assert "(192,192)" in design_doc
    assert "US8478042B2" in design_doc
    assert "mermaid" in design_doc
    assert "\\[" not in design_doc
    assert "\\operatorname" not in design_doc
    assert "\\begin{" not in design_doc
    assert "数学表达式统一使用代码块或行内代码" in design_doc
    assert "max_abs" in validate
    assert "mean_abs" in validate
    assert "p95_abs" in validate


def test_matlab_files_include_chinese_comments_and_width_markers():
    root = Path(__file__).resolve().parents[1]
    matlab_dir = root / "matlab"

    expectations = {
        "ce_hw_config.m": ["位宽", "默认值", "寄存器", "U1.10", "family_b_knots", "family_d_knots"],
        "ce_hw_control_update.m": ["输入参数", "输出参数", "位宽", "scene_id", "饱和"],
        "ce_hw_datapath.m": ["输入参数", "输出参数", "位宽", "U1.10", "饱和"],
        "ce_hw_helpers.m": ["位宽", "Q 格式", "round", "饱和"],
        "run_ce_hw_case.m": ["脚本入口", "运行外壳", "输入变量", "输出变量"],
        "run_ce_hw_batch.m": ["脚本入口", "运行外壳", "输入变量", "输出变量"],
        "validate_ce_hw_against_python.m": ["验证外壳", "不是核心硬件路径", "max_abs", "mean_abs", "p95_abs"],
    }

    for name, markers in expectations.items():
        content = (matlab_dir / name).read_text(encoding="utf-8")
        for marker in markers:
            assert marker in content, f"{name}: missing {marker}"
