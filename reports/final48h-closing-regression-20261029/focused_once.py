"""Focused follow-up only; never invokes an unselected full suite."""
from pathlib import Path
from datetime import UTC, datetime
import hashlib,importlib.util,json,os,re,signal,subprocess,time
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("closing_inventory",OUT/"full_regression_driver.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
groups=json.loads((OUT/"focused-targets.json").read_text())
env={k:v for k,v in os.environ.items() if not k.startswith(("NEBIUS_","TAVILY_","OPENAI_","ANTHROPIC_","HEADROOM_")) and not k.endswith(("_API_KEY","_API_TOKEN")) and k not in {"HF_TOKEN","HUGGING_FACE_HUB_TOKEN","PYTEST_ADDOPTS","CLOSING_GUARD_PROBE_ONLY"}}
env.update(PYTHONDONTWRITEBYTECODE="1",PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",PYTEST_ADDOPTS="-p no:cacheprovider",CUDA_VISIBLE_DEVICES="",NVIDIA_VISIBLE_DEVICES="void",HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1")
started=time.monotonic();before=module.source_hashes()
record={"schema":"headroom.closing-regression.focused.v1","started_at_utc":datetime.now(UTC).isoformat(),"source_head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),"scope":"Only previously failed/error tests; excluded two files handled independently; not a second full suite.","timebox_seconds":600,"checks":[],"guard_sha256":hashlib.sha256((OUT/"closing_guarded_v3.py").read_bytes()).hexdigest()}
with (OUT/"focused-launch.json").open("x") as h: json.dump(record,h,indent=2);h.write("\n")
(OUT/"focused-sources-before.json").write_text(json.dumps(before,indent=2)+"\n")
for label in ("non_cpu","cpu"):
    remaining=600-(time.monotonic()-started)
    if remaining<=0: break
    command=[str(ROOT/".venv/bin/python"),str(OUT/"closing_guarded_v3.py"),*groups[label]]
    item={"name":label,"command":command,"selected":len(groups[label]),"started_at_utc":datetime.now(UTC).isoformat(),"log":label+"-focused.log"}
    stage=time.monotonic()
    with (OUT/item["log"]).open("x") as log:
        child=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        print(json.dumps({"group":label,"pid":child.pid,"selected":item["selected"]}),flush=True)
        try:
            code=child.wait(timeout=remaining);item["status"]="completed"
        except subprocess.TimeoutExpired:
            item["status"]="timebox_interrupted"
            os.killpg(child.pid,signal.SIGINT)
            try:code=child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGTERM);code=child.wait(timeout=20)
    item.update(exit_code=code,elapsed_seconds=time.monotonic()-stage)
    contents=(OUT/item["log"]).read_text(errors="replace")
    item["summary"]=next((line for line in reversed(contents.splitlines()) if re.search(r"\d+ (?:passed|failed|error)",line)),None)
    item["log_sha256"]=hashlib.sha256((OUT/item["log"]).read_bytes()).hexdigest()
    record["checks"].append(item)
    (OUT/"focused-result.json").write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps({k:v for k,v in item.items() if k!="command"}),flush=True)
    if item["status"]!="completed":break
after=module.source_hashes()
(OUT/"focused-sources-after.json").write_text(json.dumps(after,indent=2)+"\n")
record.update(finished_at_utc=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-started,changed_sources=sorted(k for k in set(before)|set(after) if before.get(k)!=after.get(k)))
(OUT/"focused-result.json").write_text(json.dumps(record,indent=2)+"\n")
print(json.dumps({"finished":True,"elapsed_seconds":record["elapsed_seconds"],"changed_sources":record["changed_sources"]}),flush=True)
