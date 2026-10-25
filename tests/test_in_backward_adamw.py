"""Real torch CPU controls; no GPU or provider calls, no model-repair scores."""

import json
from pathlib import Path

import pytest

from headroom.lab.runner import run_script

PAIR_SCRIPT = """
import copy
import json
from pathlib import Path
import torch
from torch import nn
from headroom.optim.in_backward_adamw import AdamWInBackward

torch.set_num_threads(1)
torch.manual_seed(31)
class Tiny(nn.Module):
    def __init__(self):
        super().__init__()
        self.first=nn.Linear(8,12)
        self.second=nn.Linear(12,4)
        self.unused=nn.Parameter(torch.ones(3))
    def forward(self,x):
        y=self.first(x)
        return self.second(torch.nn.functional.gelu(y)+y*.1)

reference=Tiny()
candidate=copy.deepcopy(reference)
options=OPTIONS
left_params=list(reference.parameters())
right_params=list(candidate.parameters())
def groups(parameters):
    return [
        {"params":parameters[:3],"lr":.001,"weight_decay":.02},
        {"params":parameters[3:],"lr":.0003,"weight_decay":.005},
    ]
ordinary=torch.optim.AdamW(groups(left_params),foreach=False,**options)
early=AdamWInBackward(groups(right_params),**options)
inputs=torch.randn(5,8)
targets=torch.randn(5,4)
checks=[]
for index in range(20):
    ordinary.zero_grad(set_to_none=True)
    early.zero_grad(set_to_none=True)
    expected=(reference(inputs)-targets).square().mean()
    expected.backward()
    ordinary.step()
    actual=(candidate(inputs)-targets).square().mean()
    torch.testing.assert_close(actual,expected,rtol=0,atol=0)
    actual.backward()
    for left,right in zip(left_params,right_params,strict=True):
        torch.testing.assert_close(left,right,rtol=0,atol=0)
        first,second=ordinary.state.get(left,{}),early.state.get(right,{})
        assert first.keys()==second.keys()
        for name in first:
            torch.testing.assert_close(first[name],second[name],rtol=0,atol=0)
        assert right.grad is None
    checks.append(index+1)
    Path("/out/optimizer-control.json").write_text(json.dumps({
        "verified_pair_steps":checks,"parameter_and_state_exact":True,
        "loss_exact":True,"research_control_only":True,
    }))
    early.step()
    if index==7:
        saved=copy.deepcopy(early.state_dict())
        early.close()
        early=AdamWInBackward(groups(right_params),**options)
        early.load_state_dict(saved)
"""


@pytest.mark.parametrize("options", [{}, {"amsgrad": True}, {"maximize": True}])
def test_twenty_cpu_updates_match_every_parameter_and_optimizer_state(tmp_path, options):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "train.py"
    script.write_text(PAIR_SCRIPT.replace("OPTIONS", repr(options)))
    result = run_script(
        script, device="cpu", max_steps=40, max_seconds=90, run_root=tmp_path / "runs"
    )
    assert result["status"] == "completed", result
    assert result["steps"] == 40  # Two optimizers, twenty actual logical updates each.
    assert len(result["loss_series"]) == 40
    evidence = json.loads(
        (Path(result["target_artifact_dir"]) / "optimizer-control.json").read_text()
    )
    assert evidence["verified_pair_steps"] == list(range(1, 21))
    assert evidence["parameter_and_state_exact"] and evidence["loss_exact"]


def test_parameter_callbacks_do_not_inflate_lab_logical_updates(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "train.py"
    script.write_text("""
import json
from pathlib import Path
import torch
from headroom.optim.in_backward_adamw import AdamWInBackward
torch.set_num_threads(1)
model=torch.nn.Sequential(torch.nn.Linear(4,8),torch.nn.GELU(),torch.nn.Linear(8,2))
optimizer=AdamWInBackward(model.parameters(),lr=.001)
x=torch.ones(3,4)
for index in range(20):
    optimizer.zero_grad()
    loss=model(x).square().mean()
    loss.backward()
    assert optimizer.parameter_updates==(index+1)*4
    assert optimizer.logical_steps==index
    Path("/out/logical-updates.json").write_text(json.dumps({
        "parameter_updates":optimizer.parameter_updates,
        "backwards":index+1,
        "completed_logical_steps_before_boundary":optimizer.logical_steps,
    }))
    optimizer.step()
""")
    result = run_script(
        script, device="cpu", max_steps=20, max_seconds=60, run_root=tmp_path / "runs"
    )
    assert result["status"] == "completed" and result["steps"] == 20, result
    assert len(result["loss_series"]) == 20
    evidence = json.loads(
        (Path(result["target_artifact_dir"]) / "logical-updates.json").read_text()
    )
    assert evidence == {
        "parameter_updates": 80,
        "backwards": 20,
        "completed_logical_steps_before_boundary": 19,
    }


def test_unsupported_usage_fails_instead_of_silently_claiming_equivalence(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "train.py"
    script.write_text("""
import json
from pathlib import Path
import torch
from headroom.optim.in_backward_adamw import AdamWInBackward
torch.set_num_threads(1)
checks=[]
for option in ("foreach","fused","capturable","differentiable"):
    try:
        AdamWInBackward([torch.nn.Parameter(torch.ones(2))],**{option:True})
    except ValueError:
        checks.append(option)
    else:
        raise AssertionError(option)
try:
    AdamWInBackward([torch.nn.Parameter(torch.ones(2,dtype=torch.bfloat16))])
except TypeError:
    checks.append("dtype")
else:
    raise AssertionError("dtype")
p=torch.nn.Parameter(torch.ones(2))
optimizer=AdamWInBackward([p])
(p.square().sum()).backward()
try:
    (p.square().sum()).backward()
except RuntimeError as error:
    assert "Multiple backwards" in str(error)
    checks.append("accumulation")
else:
    raise AssertionError("accumulation")
optimizer.close()
Path("/out/rejected-modes.json").write_text(json.dumps(checks))
model=torch.nn.Linear(2,1)
ordinary=torch.optim.AdamW(model.parameters(),foreach=False)
for _ in range(20):
    ordinary.zero_grad()
    loss=model(torch.ones(1,2)).square().mean()
    loss.backward()
    ordinary.step()
""")
    result = run_script(
        script, device="cpu", max_steps=20, max_seconds=60, run_root=tmp_path / "runs"
    )
    assert result["status"] == "completed", result
    evidence = json.loads((Path(result["target_artifact_dir"]) / "rejected-modes.json").read_text())
    assert evidence == ["foreach", "fused", "capturable", "differentiable", "dtype", "accumulation"]
