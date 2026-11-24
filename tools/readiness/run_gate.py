"""Run the current source acceptance suites and bind results to source hashes.

This is a software gate. It does not manufacture reboot, power-loss, installed
package, native-dialog or other-platform acceptance evidence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]

def inventory():
    files=[ROOT/"Cargo.toml",ROOT/"Cargo.lock",ROOT/"rust-toolchain.toml"]
    for base in ("backend/core","backend/python/synapse_ai","backend/desktop","backend/desktop-slint","tools/release","tools/readiness"):
        files.extend(p for p in (ROOT/base).rglob("*") if p.is_file() and p.suffix in {".rs",".py",".toml",".slint",".json",".ps1"} and "__pycache__" not in p.parts)
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--include-native",action="store_true")
    args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    before=inventory()
    suites=[
        ("core",["cargo","test","--locked","-p","synapse-core","--features","test-fault-injection","--","--test-threads=1"]),
        ("python",[sys.executable,"-B","-m","unittest","discover","-s","backend/python/tests"]),
        ("slint",["cargo","test","--locked","-p","synapse-desktop-slint"]),
        ("distribution",[sys.executable,"-B","-m","unittest","discover","-s","tools/release","-p","test_distribution.py"]),
    ]
    if args.include_native:
        suites.append(("native",["cargo","test","--locked","-p","synapse-core","--features","test-fault-injection","--","--ignored","--test-threads=1"]))
    results=[]
    for name,command in suites:
        started=time.monotonic()
        environment=os.environ.copy()
        native_root=None
        if name=="native" and os.name=="nt":
            # The contained Windows linker must stage outside user-profile
            # paths. Core creates this fresh random directory with private ACLs.
            metadata=json.loads(subprocess.check_output(["cargo","metadata","--no-deps","--format-version","1"],cwd=ROOT,text=True,encoding="utf-8"))
            binary=Path(metadata["target_directory"])/"debug"/"synapse-backend.exe"
            native_root=Path(ROOT.anchor)/("synapse-check-gate-"+uuid.uuid4().hex)
            request=json.dumps({"version":1,"request_id":"private-gate-root","command":{"type":"health"}})+"\n"
            setup=subprocess.run([str(binary),"--state-dir",str(native_root),"--workspace",str(ROOT)],input=request,text=True,encoding="utf-8",capture_output=True,timeout=20)
            if setup.returncode or not json.loads(setup.stdout)["ok"]:
                raise RuntimeError("Could not create the private native test directory")
            environment.update({"TMP":str(native_root),"TEMP":str(native_root)})
        try:
            with (output/f"{name}.log").open("w",encoding="utf-8") as log:
                process=subprocess.run(command,cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT,timeout=2400)
        finally:
            if native_root is not None and native_root.parent==Path(ROOT.anchor) and re.fullmatch(r"synapse-check-gate-[0-9a-f]{32}",native_root.name):
                try:
                    if native_root.is_symlink() or native_root.is_junction() or native_root.resolve(strict=True)!=native_root:
                        raise OSError("Native test directory identity changed")
                    shutil.rmtree(native_root)
                except OSError:print("Owned native test directory retained for diagnosis",flush=True)
        text=(output/f"{name}.log").read_text(encoding="utf-8",errors="replace")
        summaries=re.findall(r"(?m)^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored",text)
        passed=process.returncode==0 and not any(row[0]=="FAILED" for row in summaries)
        results.append({"suite":name,"pass":passed,"exit_code":process.returncode,"elapsed_ms":round(1000*(time.monotonic()-started)),"framework_summaries":summaries})
        print(json.dumps(results[-1]),flush=True)
        if not passed:break
    stable=before==inventory()
    report={"version":1,"platform":sys.platform,"source_files":before,"source_stable":stable,"suites":results,"pass":stable and len(results)==len(suites) and all(row["pass"] for row in results),"excluded_acceptance":["installed_package","real_model_evals","native_consent_dialog","host_reboot","abrupt_power_loss","other_platform_hardware"]}
    (output/"gate.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 0 if report["pass"] else 1

if __name__=="__main__":sys.exit(main())
