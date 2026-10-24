"""Static honesty is tested without importing torch or executing target code."""

import pytest

from headroom.verify.policy import (
    PatchPolicy,
    check_cli_changes,
    check_parameter_counts,
    check_source_changes,
    merge_cli_changes,
    safe_relative_path,
    validate_env_changes,
)


def check(before, after, **policy):
    return check_source_changes(
        {"train.py": before}, {"train.py": after}, policy=PatchPolicy(**policy)
    )


@pytest.mark.parametrize(
    "before,after,code",
    [
        ("n_layer = 24\n", "n_layer = 12\n", "MODEL_SHRUNK"),
        ("vocab_size = 50000\n", "vocab_size = 1000\n", "MODEL_SHRUNK"),
        ("max_steps = 20\n", "max_steps = 1\n", "TRAINING_TRUNCATED"),
        ("model = nn.Linear(128, 128)\n", "model = nn.Linear(64, 64)\n", "MODEL_SHRUNK"),
        ("N=24\nn_layer=N\n", "N=24\nn_layer=N//2\n", "MODEL_SHRUNK"),
        (
            "for step in range(20):\n    train()\n",
            "for step in range(1):\n    train()\n",
            "TRAINING_TRUNCATED",
        ),
        ("loss.backward()\noptimizer.step()\n", "loss.backward()\n", "TRAINING_TRUNCATED"),
        (
            "for step in range(20):\n    train()\n",
            "for step in range(20):\n    train()\n    break\n",
            "TRAINING_TRUNCATED",
        ),
    ],
)
def test_cheating_changes_have_concrete_reason_codes(before, after, code):
    verdict = check(before, after)
    assert not verdict.allowed
    assert code in {issue.code for issue in verdict.issues}


@pytest.mark.parametrize(
    "before,after",
    [
        ("total_loss += loss\n", "total_loss += loss.item()\n"),
        ("y = model(x)\n", "with torch.no_grad():\n    y = model(x)\n"),
        (
            "opt = torch.optim.AdamW(model.parameters())\n",
            "opt = torch.optim.AdamW(model.parameters(), foreach=False)\n",
        ),
        (
            "y = block(x)\n",
            "y = torch.utils.checkpoint.checkpoint(block, x, use_reentrant=False)\n",
        ),
        ("ref = model.to('cuda')\n", "ref = model.to('cpu')\n"),
        ("batch_size=32\ngrad_accum_steps=1\n", "batch_size=4\ngrad_accum_steps=8\n"),
        ("n_layer = 24\nx=1\n", "n_layer = 24\nx=2\n"),
    ],
)
def test_normal_memory_repairs_are_not_rejected(before, after):
    verdict = check(before, after)
    assert verdict.allowed, verdict.issues


@pytest.mark.parametrize(
    "after",
    [
        "with torch.autocast('cuda'):\n    y=model(x)\n",
        "y=x.to(dtype=torch.bfloat16)\n",
        "from torch import autocast as ac\nwith ac('cuda'):\n    y=model(x)\n",
    ],
)
def test_precision_changes_require_explicit_permission(after):
    assert "NUMERICS_CHANGE_FORBIDDEN" in {i.code for i in check("y=model(x)\n", after).issues}
    assert check("y=model(x)\n", after, allow_numerics_change=True).allowed


def test_reduced_batch_without_compensating_accumulation_is_not_a_repair():
    verdict = check("batch_size=32\ngrad_accum_steps=1\n", "batch_size=4\ngrad_accum_steps=1\n")
    assert "EFFECTIVE_BATCH_CHANGED" in {i.code for i in verdict.issues}


@pytest.mark.parametrize(
    "after,code",
    [
        ("import socket\n", "NETWORK_OR_PROCESS_FORBIDDEN"),
        (
            "import requests as r\nr.get('https://example.invalid')\n",
            "NETWORK_OR_PROCESS_FORBIDDEN",
        ),
        ("import os\nos.system('echo dangerous')\n", "NETWORK_OR_PROCESS_FORBIDDEN"),
        ("from pathlib import Path\nPath('/tmp/escape').write_text('x')\n", "FILESYSTEM_ESCAPE"),
        ("open('../escape', 'w').write('x')\n", "FILESYSTEM_ESCAPE"),
        ("open('relative-output', 'w').write('x')\n", "FILESYSTEM_ESCAPE"),
        ("x=os.environ['NEBIUS_API_KEY']\n", "SECRET_ACCESS_FORBIDDEN"),
    ],
)
def test_new_network_secret_or_filesystem_escape_operations_are_rejected(after, code):
    verdict = check("x=1\n", after)
    assert code in {i.code for i in verdict.issues}


def test_authorized_model_change_requires_disclosure():
    before, after = {"train.py": "n_layer=12\n"}, {"train.py": "n_layer=6\n"}
    policy = PatchPolicy(allow_model_change=True)
    assert not check_source_changes(before, after, policy=policy).allowed
    assert check_source_changes(
        before, after, policy=policy, notes=["MODEL_CHANGE_APPROVED: explicit alternate model"]
    ).allowed


def test_parameter_count_evidence_is_not_optional_or_a_full_equivalence_proof():
    assert check_parameter_counts(100, 100).allowed
    assert not check_parameter_counts(None, 100).allowed
    assert check_parameter_counts(100, 50).issues[0].code == "MODEL_SHRUNK"
    assert check_parameter_counts(100, 101).issues[0].code == "MODEL_CHANGED"
    assert not check_parameter_counts(True, 1).allowed
    assert check_parameter_counts(100, 100).requires_runtime_verification


def test_config_model_shrink_is_checked():
    verdict = check_source_changes(
        {"config.json": '{"vocab_size": 50000}\n'}, {"config.json": '{"vocab_size": 1000}\n'}
    )
    assert verdict.issues[0].code == "MODEL_SHRUNK"


def test_cli_controls_and_narrow_policy_veto():
    assert check_cli_changes(
        ["--batch_size", "32"], ["--batch_size", "4", "--gradient_accumulation_steps", "8"]
    ).allowed
    assert not check_cli_changes(
        [], ["--batch_size", "4"], policy=PatchPolicy(allow_batch_change=False)
    ).allowed
    assert not check_cli_changes(["--max_steps", "20"], ["--max_steps", "1"]).allowed
    assert not check_cli_changes([], ["--bf16"]).allowed
    assert not check_cli_changes([], ["--foo", "$(touch dangerous)"]).allowed
    assert merge_cli_changes(
        ["train.py", "--batch_size=32", "--max_steps=20"], ["--batch_size", "4"]
    ) == ["train.py", "--batch_size", "4", "--max_steps", "20"]


def test_env_allowlist_and_path_protection(tmp_path):
    assert not validate_env_changes({"PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"})
    assert validate_env_changes({"LD_PRELOAD": "/tmp/evil.so"})
    assert validate_env_changes({"PYTORCH_CUDA_ALLOC_CONF": "unknown:True"})
    for name in ("../bad.py", ".git/config", ".env", "credentials.json", "/tmp/bad.py", "a\\b.py"):
        with pytest.raises(ValueError):
            safe_relative_path(name, tmp_path)


@pytest.mark.parametrize(
    "text,code",
    [
        ("import socket\n", "NETWORK_OR_PROCESS_FORBIDDEN"),
        ("from dotenv import load_dotenv\nload_dotenv()\n", "ENV_FILE_ACCESS"),
        ("x=open('.env').read()\n", "ENV_FILE_ACCESS"),
        ("api_key='" + "sk-" + "a" * 24 + "'\n", "EMBEDDED_CREDENTIAL"),
        ("TOKEN='" + "tvly-" + "b" * 24 + "'\n", "EMBEDDED_CREDENTIAL"),
    ],
)
def test_source_upload_preflight_denies_without_echoing_source(text, code):
    from headroom.verify.policy import scan_source_forbidden

    report = scan_source_forbidden({"upload.py": text})
    assert not report.allowed and code in {issue.code for issue in report.issues}
    assert text not in str(report)
    assert "a" * 24 not in str(report) and "b" * 24 not in str(report)


def test_source_preflight_ignores_env_file_without_reading_it(tmp_path, monkeypatch):
    from pathlib import Path

    from headroom.verify.policy import scan_source_forbidden

    (tmp_path / "train.py").write_text("x=1\n")
    (tmp_path / ".env").write_text("never read this file")
    original = Path.read_text

    def guarded(path, *args, **kwargs):
        assert path.name != ".env", "secret file was read"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded)
    assert scan_source_forbidden(tmp_path).allowed


def test_source_preflight_only_reads_explicit_files(tmp_path):
    from headroom.verify.policy import scan_source_forbidden

    (tmp_path / "train.py").write_text("import torch\nloss=model(x).sum()\nloss.backward()\n")
    (tmp_path / "prepare.py").write_text("import requests\n")
    assert not scan_source_forbidden(tmp_path).allowed
    assert scan_source_forbidden(tmp_path, source_files=["train.py"]).allowed


@pytest.mark.parametrize(
    "path,before,after",
    [
        ("train.py", 'dtype="float32"\n', 'dtype="bfloat16"\n'),
        ("train.py", "x=model(x)\n", 'x=model(x, dtype="bf16")\n'),
        ("config.json", '{"dtype": "float32"}', '{"dtype": "bfloat16"}'),
    ],
)
def test_string_precision_controls_require_permission(path, before, after):
    report = check_source_changes({path: before}, {path: after})
    assert not report.allowed
    assert "NUMERICS_CHANGE_FORBIDDEN" in {i.code for i in report.issues}


@pytest.mark.parametrize("method", ["read_text", "read_bytes"])
def test_pathlib_escape_reads_rejected_in_diff_and_upload(method):
    from headroom.verify.policy import scan_source_forbidden

    after = f'from pathlib import Path\ntext=Path("/etc/passwd").{method}()\n'
    for report in (check("x=1\n", after), scan_source_forbidden({"upload.py": after})):
        assert not report.allowed and "FILESYSTEM_ESCAPE" in {i.code for i in report.issues}


def test_large_numeric_literal_is_unknown_without_crashing():
    report = check("n_layer=12\n", "n_layer=" + "9" * 400 + "\n")
    assert not report.allowed and "MODEL_CHANGED" in {i.code for i in report.issues}


def test_method_eval_is_not_builtin_eval():
    from headroom.verify.policy import scan_source_forbidden

    assert scan_source_forbidden({"train.py": "teacher=Classifier(10).eval()\n"}).allowed
    assert not scan_source_forbidden({"train.py": "x=eval('1+1')\n"}).allowed


def test_uppercase_python_extension_is_still_checked():
    from headroom.verify.policy import scan_source_forbidden

    assert not scan_source_forbidden({"TRAIN.PY": "import socket\n"}).allowed
    assert not check_source_changes({"TRAIN.PY": "x=1\n"}, {"TRAIN.PY": "import socket\n"}).allowed


def test_all_real_scenarios_are_accepted_by_strict_source_preflight():
    from pathlib import Path

    from headroom.verify.policy import scan_source_forbidden

    root = Path(__file__).resolve().parents[1]
    paths = sorted((root / "scenarios").glob("*/train.py"))
    assert len(paths) == 8
    for path in paths:
        report = scan_source_forbidden({path.name: path.read_text()})
        assert report.allowed, (str(path), report.issues)


def test_pinned_nanogpt_profile_is_explicit_sandbox_only_and_scope_limited(tmp_path):
    import shutil
    from pathlib import Path

    from headroom.verify.policy import scan_source_forbidden

    root = Path(__file__).resolve().parents[1] / ".cache/upstream/nanoGPT"
    if not root.is_dir():
        pytest.skip("Pinned local nanoGPT checkout not present")
    selected = ["train.py", "model.py", "configurator.py"]
    assert not scan_source_forbidden(root, source_files=selected).allowed
    assert not scan_source_forbidden(
        root, source_files=selected, source_profile="pinned_nanogpt"
    ).allowed
    assert scan_source_forbidden(
        root, source_files=selected, source_profile="pinned_nanogpt", sandboxed=True
    ).allowed
    assert not scan_source_forbidden(
        {"train.py": "x=1\n"}, source_profile="pinned_nanogpt", sandboxed=True
    ).allowed
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    for name in selected:
        shutil.copyfile(root / name, candidate / name)
    train = candidate / "train.py"
    train.write_text(train.read_text() + "\nimport socket\n")
    report = scan_source_forbidden(
        candidate, source_files=selected, source_profile="pinned_nanogpt", sandboxed=True
    )
    assert not report.allowed and "NETWORK_OR_PROCESS_FORBIDDEN" in {i.code for i in report.issues}
    (candidate / "configurator.py").write_text("x=1\n")
    assert (
        scan_source_forbidden(
            candidate, source_files=selected, source_profile="pinned_nanogpt", sandboxed=True
        )
        .issues[0]
        .code
        == "SOURCE_PROFILE_UNVERIFIED"
    )


def test_nanogpt_cli_rejects_config_files_and_formats_overrides():
    from headroom.verify.policy import nanogpt_cli

    assert nanogpt_cli(["python", "train.py", "--batch_size=4"]) == [
        "python",
        "train.py",
        "--batch_size=4",
    ]
    assert nanogpt_cli(["--batch_size", "4"], require_equals=False) == ["--batch_size=4"]
    for argv in (
        ["config/override.py"],
        ["--batch_size", "4"],
        ["--compile"],
        ["python", "other.py"],
    ):
        with pytest.raises(ValueError):
            nanogpt_cli(argv)


def test_real_s1_tuple_model_shrink_is_detected():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scenarios/s1_batch_too_big/train.py"
    before = path.read_text()
    after = before.replace("(256, 192, 2048)", "(256, 96, 2048)")
    assert before != after
    verdict = check(before, after)
    assert not verdict.allowed and "MODEL_SHRUNK" in {i.code for i in verdict.issues}


def test_real_s1_steps_cli_is_protected():
    assert not check_cli_changes(["--steps", "20"], ["--steps", "1"]).allowed


@pytest.mark.parametrize(
    "before,after",
    [
        ("width, depth = 256, 192\n", "width, depth = 256, 96\n"),
        (
            "width, depth = (32, 2) if tiny else (256, 192)\n",
            "width, depth = (256, 192) if tiny else (32, 2)\n",
        ),
    ],
)
def test_destructured_shape_values_keep_branch_order(before, after):
    assert not check(before, after).allowed


def test_annotation_only_values_do_not_crash():
    assert check("width: int\nx=1\n", "width: int\nx=2\n").allowed


def test_reviewed_nanogpt_cache_supports_clean_install_without_upstream(tmp_path, monkeypatch):
    import shutil
    from pathlib import Path

    import headroom.verify.policy as module

    original = Path(module.__file__).resolve().parents[2] / ".cache/upstream/nanoGPT"
    if not original.is_dir():
        pytest.skip("Pinned original files not present")
    project = tmp_path / "project"
    reviewed = project / ".cache/reviewed/nanogpt" / module.NANOGPT_REF
    reviewed.mkdir(parents=True)
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    for name in module.NANOGPT_HASHES:
        shutil.copyfile(original / name, reviewed / name)
        shutil.copyfile(original / name, candidate / name)
    monkeypatch.setattr(module, "__file__", str(project / "headroom/verify/policy.py"))
    assert module.scan_source_forbidden(
        candidate,
        source_files=["train.py", "model.py"],
        source_profile="pinned_nanogpt",
        sandboxed=True,
    ).allowed
    (reviewed / "train.py").write_text("x=1\n")
    assert not module.scan_source_forbidden(
        candidate, source_files=["train.py"], source_profile="pinned_nanogpt", sandboxed=True
    ).allowed


def test_reviewed_nanogpt_cache_rejects_symlink_baseline(tmp_path, monkeypatch):
    from pathlib import Path

    import headroom.verify.policy as module

    original = Path(module.__file__).resolve().parents[2] / ".cache/upstream/nanoGPT"
    if not original.is_dir():
        pytest.skip("Pinned original files not present")
    project = tmp_path / "project"
    reviewed = project / ".cache/reviewed/nanogpt" / module.NANOGPT_REF
    reviewed.parent.mkdir(parents=True)
    reviewed.symlink_to(original, target_is_directory=True)
    monkeypatch.setattr(module, "__file__", str(project / "headroom/verify/policy.py"))
    assert not module.scan_source_forbidden(
        original, source_files=["train.py"], source_profile="pinned_nanogpt", sandboxed=True
    ).allowed
