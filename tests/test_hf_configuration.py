"""Static HF configuration acceptance uses real pinned source, never torch imports."""

import hashlib
from pathlib import Path

import pytest

from headroom.acceptance.hf_configuration import check_hf_configuration

ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / "repos/hf_trainer/train.py").read_text()
BASE_SHA = hashlib.sha256(BASE.encode()).hexdigest()


def check(after, **kwargs):
    return check_hf_configuration(
        {"train.py": BASE}, {"train.py": after}, expected_source_sha256=BASE_SHA, **kwargs
    )


def test_real_fixture_checkpoint_and_bf16_are_configuration_only():
    result = check(
        BASE.replace("gradient_checkpointing=False", "gradient_checkpointing=True").replace(
            "bf16=False", "bf16=True"
        )
    )
    assert result["accepted"] is True
    assert result["changed_lines"] == 4
    assert result["changed_arguments"] == ["bf16", "gradient_checkpointing"]
    assert "hardware" in result["scope"]


def test_batch_accumulation_and_checkpoint_kwargs_are_recognized():
    after = (
        BASE.replace(
            "per_device_train_batch_size=args.batch_size or (16 if full else 2)",
            "per_device_train_batch_size=args.batch_size or (4 if full else 2)",
        )
        .replace("gradient_accumulation_steps=1", "gradient_accumulation_steps=4")
        .replace(
            "gradient_checkpointing=False,",
            'gradient_checkpointing=True,\n        gradient_checkpointing_kwargs={"use_reentrant": False},',
        )
    )
    result = check(after)
    assert result["accepted"] is True
    assert result["changed_lines"] == 7


@pytest.mark.parametrize(
    "old,new",
    [
        ("n_layer=24", "n_layer=12"),
        ("max_steps=20", "max_steps=1"),
        ("learning_rate=1e-4", "learning_rate=1e-2"),
        ("tokens.clone()", "tokens"),
        ("trainer.train()", "pass"),
        ("set_seed(1337)", "set_seed(7)"),
        ("SyntheticTokens(1024", "SyntheticTokens(16"),
    ],
)
def test_non_configuration_semantics_cannot_pass(old, new):
    assert check(BASE.replace(old, new))["accepted"] is False


@pytest.mark.parametrize(
    "value", ["evil()", "__import__('os').system('echo unsafe')", "args.device", "float('nan')"]
)
def test_configuration_values_cannot_introduce_calls(value):
    result = check(BASE.replace("bf16=False", "bf16=" + value))
    assert result["accepted"] is False
    assert "executable_or_unrecognized_configuration_value" in result["reasons"]


def test_original_pin_file_set_and_line_limit():
    after = BASE.replace("bf16=False", "bf16=True")
    assert (
        check_hf_configuration(
            {"train.py": BASE}, {"train.py": after}, expected_source_sha256="0" * 64
        )["accepted"]
        is False
    )
    assert (
        check_hf_configuration(
            {"train.py": BASE}, {"train.py": after, "extra.py": ""}, expected_source_sha256=BASE_SHA
        )["accepted"]
        is False
    )
    assert check(after, max_changed_lines=1)["configuration_only"] is True
    assert check(after, max_changed_lines=1)["accepted"] is False
    assert check(after, max_changed_lines=16)["accepted"] is False


def test_comments_count_toward_line_bound_and_noop_is_not_repair():
    assert check(BASE)["accepted"] is False
    result = check(BASE.replace("bf16=False", "bf16=True") + "\n" + "# extra\n" * 15)
    assert result["configuration_only"] is True
    assert result["within_changed_line_limit"] is False


def test_expanded_keywords_and_invalid_python_are_rejected():
    assert check(BASE.replace("bf16=False,", "bf16=False, **evil,"))["accepted"] is False
    assert check(BASE + "\nthis is not python !")["accepted"] is False
