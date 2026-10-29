"""Single authorized closing full suite, with immutable launch and result records."""
from pathlib import Path
from datetime import UTC, datetime
import hashlib, json, os, signal, subprocess, time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
EXPECTED = "e6cf7a220bd59846e74e057a1a972526e514e2ed"
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
if head != EXPECTED:
    raise RuntimeError("Closing source HEAD differs from authorized revision")
preflight=json.loads((OUT/"preflight.json").read_text())
if not preflight.get("guard_probe_passed"):
    raise RuntimeError("Closing guard probe is not passing")
env={k:v for k,v in os.environ.items() if not k.startswith(("NEBIUS_","TAVILY_","OPENAI_","ANTHROPIC_","HEADROOM_")) and not k.endswith(("_API_KEY","_API_TOKEN")) and k not in {"HF_TOKEN","HUGGING_FACE_HUB_TOKEN","PYTEST_ADDOPTS","CLOSING_GUARD_PROBE_ONLY"}}
env.update(PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTEST_ADDOPTS="-p no:cacheprovider", CUDA_VISIBLE_DEVICES="", NVIDIA_VISIBLE_DEVICES="void", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
command=[str(ROOT/".venv/bin/python"),str(OUT/"full_regression_driver.py")]
started=time.monotonic()
record={
 "schema":"headroom.closing-regression.launch.v1",
 "started_at_utc":datetime.now(UTC).isoformat(),
 "source_head":head,
 "command":command,
 "pytest_command":["pytest","-q"],
 "pytest_extra_environment_options":["-p","no:cacheprovider"],
 "selected_tests":None,
 "unfiltered_full_suite":True,
 "max_seconds":1800,
 "provider_environment_removed":True,
 "pytest_plugin_autoload_disabled":True,
 "no_second_full_run":True,
}
with (OUT/"launch.json").open("x") as handle:
    json.dump(record,handle,indent=2); handle.write("\n")
preflight["full_run_started"]=True
(OUT/"preflight.json").write_text(json.dumps(preflight,indent=2)+"\n")
with (OUT/"driver-output.log").open("x") as output:
    child=subprocess.Popen(command,cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
    print(json.dumps({"driver_pid":child.pid,"launch":str(OUT/"launch.json")}),flush=True)
    try:
        code=child.wait(timeout=1800)
        reason="completed"
    except subprocess.TimeoutExpired:
        reason="timebox_interrupted"
        os.killpg(child.pid,signal.SIGINT)
        try: code=child.wait(timeout=45)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGTERM)
            code=child.wait(timeout=20)
record.update(finished_at_utc=datetime.now(UTC).isoformat(),exit_code=code,elapsed_seconds=time.monotonic()-started,status=reason)
record["guard_sha256"]=hashlib.sha256((OUT/"closing_guarded.py").read_bytes()).hexdigest()
(OUT/"launch-result.json").write_text(json.dumps(record,indent=2)+"\n")
print(json.dumps(record),flush=True)
raise SystemExit(code)
