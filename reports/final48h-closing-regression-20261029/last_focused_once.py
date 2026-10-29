"""Finish selected focused checks inside the original shared 600-second window."""
from pathlib import Path
from datetime import UTC,datetime
import hashlib,importlib.util,json,os,re,signal,subprocess,time
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("closing_inventory",OUT/"full_regression_driver.py");m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
groups=json.loads((OUT/"last-focused-targets.json").read_text())
launch=json.loads((OUT/"focused-launch.json").read_text())
deadline=datetime.fromisoformat(launch["started_at_utc"]).timestamp()+600
env={k:v for k,v in os.environ.items() if not k.startswith(("NEBIUS_","TAVILY_","OPENAI_","ANTHROPIC_","HEADROOM_")) and not k.endswith(("_API_KEY","_API_TOKEN")) and k not in {"HF_TOKEN","HUGGING_FACE_HUB_TOKEN","PYTEST_ADDOPTS","CLOSING_GUARD_PROBE_ONLY"}}
env.update(PYTHONDONTWRITEBYTECODE="1",PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",PYTEST_ADDOPTS="-p no:cacheprovider",CUDA_VISIBLE_DEVICES="",NVIDIA_VISIBLE_DEVICES="void",HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1")
record={"schema":"headroom.closing-regression.remaining-focused.v1","started_at_utc":datetime.now(UTC).isoformat(),"original_shared_deadline_utc":datetime.fromtimestamp(deadline,UTC).isoformat(),"guard_sha256":hashlib.sha256((OUT/"closing_guarded_v4.py").read_bytes()).hexdigest(),"checks":[]}
before=m.source_hashes();(OUT/"last-focused-sources-before.json").write_text(json.dumps(before,indent=2)+"\n")
try:
    for label,targets in groups.items():
        remaining=deadline-time.time()
        if remaining<2:
            record["stop_reason"]="original_shared_timebox_exhausted";break
        command=[str(ROOT/".venv/bin/python"),str(OUT/"closing_guarded_v4.py"),*targets]
        item={"name":label,"command":command,"selected":len(targets),"started_at_utc":datetime.now(UTC).isoformat(),"log":label+"-focused.log"}
        stage=time.monotonic()
        with (OUT/item["log"]).open("x") as log:
            child=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            item["pid"]=child.pid;record["active"]=item
            (OUT/"last-focused-result.json").write_text(json.dumps(record,indent=2)+"\n")
            try:
                code=child.wait(timeout=remaining);item["status"]="completed"
            except subprocess.TimeoutExpired:
                item["status"]="timebox_interrupted";os.killpg(child.pid,signal.SIGINT)
                try:code=child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid,signal.SIGTERM);code=child.wait(timeout=20)
        item.update(exit_code=code,elapsed_seconds=time.monotonic()-stage)
        contents=(OUT/item["log"]).read_text(errors="replace")
        item["summary"]=next((line for line in reversed(contents.splitlines()) if re.search(r"\d+ (?:passed|failed|error)",line)),None)
        item["log_sha256"]=hashlib.sha256((OUT/item["log"]).read_bytes()).hexdigest()
        record["checks"].append(item);record.pop("active",None)
        (OUT/"last-focused-result.json").write_text(json.dumps(record,indent=2)+"\n")
        if item["status"]!="completed":break
except BaseException as error:
    record["runner_error"]={"type":type(error).__name__,"message":str(error)}
    raise
finally:
    after=m.source_hashes()
    (OUT/"last-focused-sources-after.json").write_text(json.dumps(after,indent=2)+"\n")
    record.update(finished_at_utc=datetime.now(UTC).isoformat(),changed_sources=sorted(k for k in set(before)|set(after) if before.get(k)!=after.get(k)))
    (OUT/"last-focused-result.json").write_text(json.dumps(record,indent=2)+"\n")
