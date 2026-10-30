"""Static configuration-source discovery retains the source collector trust boundary."""

import hashlib

import pytest

from headroom import evidence


def captured(tmp_path, modules, *, command=None, cwd="/source"):
    run = tmp_path / "run"
    source = run / "source"
    source.mkdir(parents=True)
    files = {}
    for name, text in modules.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        files[name] = {"sha256": hashlib.sha256(text.encode()).hexdigest()}
    manifest = {
        "command": command or ["python", "train.py"],
        "source": {"files": files},
    }
    if cwd is not None:
        manifest["execution_entrypoint"] = {"complete": True, "startup_cwd": cwd}
    return run, manifest


def paths(run, manifest):
    sources, warnings = evidence.collect_sources(run, manifest, {})
    return {row["path"] for row in sources}, warnings, sources


def test_literal_config_and_its_imports_are_source_only(tmp_path):
    run, manifest = captured(
        tmp_path,
        {
            "train.py": 'exec(open("settings.py", encoding="utf-8").read())\n',
            "settings.py": "import settings_helper\nraise AssertionError('never execute')\n",
            "settings_helper.py": "BATCH_SIZE = 32\n",
        },
    )
    actual, warnings, sources = paths(run, manifest)
    assert actual == {"train.py", "settings.py", "settings_helper.py"}
    assert not warnings
    observation = sources[0]["static_observations"][0]
    assert observation["kind"] == "static_source_dependency"
    assert observation["path"] == "settings.py"
    assert "applied configuration remain unverified" in observation["note"]
    for row in sources:
        assert row["sha256"] == manifest["source"]["files"][row["path"]]["sha256"]


@pytest.mark.parametrize(
    "cwd,expected",
    [("/source", "settings.py"), ("/source/pkg", "pkg/settings.py")],
)
def test_literal_paths_use_captured_cwd_not_referring_file_parent(tmp_path, cwd, expected):
    run, manifest = captured(
        tmp_path,
        {
            "pkg/train.py": 'exec(open("settings.py").read())\n',
            "settings.py": "ROOT_SETTINGS = True\n",
            "pkg/settings.py": "PACKAGE_SETTINGS = True\n",
        },
        command=["python", "pkg/train.py"],
        cwd=cwd,
    )
    actual, warnings, _ = paths(run, manifest)
    assert actual == {"pkg/train.py", expected}
    assert not warnings


@pytest.mark.parametrize("cwd", [None, "/outside", "/source/../outside"])
def test_unknown_or_outside_startup_cwd_does_not_guess_a_dependency(tmp_path, cwd):
    run, manifest = captured(
        tmp_path,
        {"train.py": 'exec(open("settings.py").read())\n', "settings.py": "VALUE = 1\n"},
        cwd=cwd,
    )
    actual, warnings, _ = paths(run, manifest)
    assert actual == {"train.py"}
    assert any("launch cwd unavailable" in text for text in warnings)


def test_changed_working_directory_is_explicitly_unknown(tmp_path):
    run, manifest = captured(
        tmp_path,
        {
            "train.py": 'import os\nos.chdir("pkg")\nexec(open("settings.py").read())\n',
            "settings.py": "VALUE = 1\n",
            "pkg/settings.py": "VALUE = 2\n",
        },
    )
    actual, warnings, _ = paths(run, manifest)
    assert actual == {"train.py"}
    assert any("working directory" in text for text in warnings)


@pytest.mark.parametrize(
    "expression",
    [
        'exec(open("../outside.py").read())',
        'exec(open("/outside.py").read())',
        'exec(open(".env.py").read())',
        'exec(open("secrets/settings.py").read())',
        'exec(open("credentials/settings.py").read())',
        'exec(open(".git/settings.py").read())',
        'exec(open("settings.txt").read())',
        "exec(open(name).read())",
        'exec(open(f"settings.py").read())',
        'exec(open("settings" + ".py").read())',
        'exec(open("settings.py", "w").read())',
        'exec(open("settings.py", mode="a").read())',
        'value = open("settings.py").read()',
    ],
)
def test_unsafe_dynamic_and_ordinary_reads_do_not_expand_collection(
    tmp_path, monkeypatch, expression
):
    run, manifest = captured(
        tmp_path,
        {
            "train.py": expression + "\n",
            "settings.py": "PRIVATE_MARKER = 'not-for-collection'\n",
            ".env.py": "SECRET_MARKER = 'not-for-collection'\n",
            "secrets/settings.py": "SECRET_MARKER = 'not-for-collection'\n",
            "credentials/settings.py": "SECRET_MARKER = 'not-for-collection'\n",
            ".git/settings.py": "SECRET_MARKER = 'not-for-collection'\n",
        },
    )
    manifest["source"]["files"].update(
        {name: {} for name in ("../outside.py", "/outside.py", "settings.txt")}
    )
    calls = []
    reader = evidence._read_source

    def observed(root, relative):
        calls.append(relative)
        return reader(root, relative)

    monkeypatch.setattr(evidence, "_read_source", observed)
    actual, _, sources = paths(run, manifest)
    assert actual == {"train.py"}
    assert calls == ["train.py"]
    assert "SECRET_MARKER" not in repr(sources)
    assert "PRIVATE_MARKER" not in repr(sources)


@pytest.mark.parametrize("directory_link", [False, True])
def test_dependency_symlinks_cannot_disclose_outside_source(tmp_path, directory_link):
    dependency = "linked/settings.py" if directory_link else "settings.py"
    run, manifest = captured(tmp_path, {"train.py": f"exec(open({dependency!r}).read())\n"})
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "settings.py").write_text("OUTSIDE_MARKER = 'never read'\n")
    if directory_link:
        (run / "source" / "linked").symlink_to(outside, target_is_directory=True)
    else:
        (run / "source" / "settings.py").symlink_to(outside / "settings.py")
    manifest["source"]["files"][dependency] = {}
    actual, warnings, sources = paths(run, manifest)
    assert actual == {"train.py"}
    assert any("excluded" in text for text in warnings)
    assert "OUTSIDE_MARKER" not in repr(sources)


def test_unlisted_dependency_is_not_read(tmp_path):
    run, manifest = captured(
        tmp_path,
        {"train.py": 'exec(open("settings.py").read())\n', "settings.py": "VALUE = 1\n"},
    )
    del manifest["source"]["files"]["settings.py"]
    actual, _, _ = paths(run, manifest)
    assert actual == {"train.py"}


def test_config_hash_change_still_fails_closed(tmp_path):
    run, manifest = captured(
        tmp_path,
        {"train.py": 'exec(open("settings.py").read())\n', "settings.py": "VALUE = 1\n"},
    )
    (run / "source" / "settings.py").write_text("VALUE = 2\n")
    with pytest.raises(ValueError, match="hash differs"):
        paths(run, manifest)


def test_exec_dependency_chain_shares_existing_module_limit(tmp_path, monkeypatch):
    modules = {
        "train.py": 'exec(open("a.py").read())\n',
        "a.py": 'exec(open("b.py").read())\n',
        "b.py": 'exec(open("c.py").read())\n',
        "c.py": 'exec(open("a.py").read())\n',
    }
    run, manifest = captured(tmp_path, modules)
    monkeypatch.setattr(evidence, "MAX_SOURCE_FILES", 3)
    actual, warnings, _ = paths(run, manifest)
    assert actual == {"train.py", "a.py", "b.py"}
    assert any("module safety limit" in text for text in warnings)


def test_exec_dependency_shares_existing_file_and_total_byte_limits(tmp_path, monkeypatch):
    run, manifest = captured(
        tmp_path,
        {"train.py": 'exec(open("settings.py").read())\n', "settings.py": "#" * 90},
    )
    monkeypatch.setattr(evidence, "MAX_SOURCE_FILE_BYTES", 80)
    actual, warnings, _ = paths(run, manifest)
    assert actual == {"train.py"}
    assert any("regular file" in text for text in warnings)
    monkeypatch.setattr(evidence, "MAX_SOURCE_FILE_BYTES", 1000)
    monkeypatch.setattr(evidence, "MAX_SOURCE_TOTAL_BYTES", 100)
    actual, warnings, _ = paths(run, manifest)
    assert actual == {"train.py"}
    assert any("MiB safety limit" in text for text in warnings)
