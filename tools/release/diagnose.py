"""Read-only dependency diagnostics: never start providers, load models or write user state."""
import argparse
import ast
import ctypes
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys


def checked_local_path(value,directory):
    path=Path(value)
    if not path.is_absolute() or '..' in path.parts or '\0' in str(path) or '"' in str(path) or (os.name=='nt' and path.drive.startswith('\\\\')):
        raise ValueError('voice_config_invalid')
    for item in (path,*path.parents):
        if item.is_symlink() or item.is_junction():
            raise ValueError('voice_config_invalid')
    if not (path.is_dir() if directory else path.is_file()):
        raise ValueError('voice_config_unavailable')
    return path


def voice_configuration(config_root=None):
    root=config_root or os.environ.get('SYNAPSE_CONFIG_ROOT') or (str(Path(os.environ['LOCALAPPDATA'])/'Synapse') if os.environ.get('LOCALAPPDATA') else None)
    value={}
    source='environment' if os.environ.get('SYNAPSE_VOICE_PYTHON') else 'not_configured'
    if root:
        path=Path(root)/'voice-runtime.json'
        if path.exists() or path.is_symlink() or path.is_junction():
            checked_local_path(str(path),False)
            if path.stat().st_size>16384:
                raise ValueError('voice_config_invalid')
            value=json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(value,dict) or set(value)!={'python','models'} or any(not isinstance(item,str) for item in value.values()):
                raise ValueError('voice_config_invalid')
            checked_local_path(value['python'],False)
            checked_local_path(value['models'],True)
            source='voice-runtime.json'
    python=os.environ.get('SYNAPSE_VOICE_PYTHON') or value.get('python')
    models=os.environ.get('SYNAPSE_VOICE_MODELS') or value.get('models')
    if python:
        path=checked_local_path(python,False)
        if os.name=='nt' and path.name.casefold()!='python.exe':
            raise ValueError('voice_config_invalid')
    if models:
        checked_local_path(models,True)
    return python,models,source


def optional_capabilities(programs,config_root=None):
    """Inspect configuration/dependency presence without importing ML runtimes."""
    dependencies={}
    for name in ('pocketsphinx','faster_whisper','supertonic','playwright'):
        try:
            dependencies[name]=importlib.util.find_spec(name) is not None
        except (ImportError,ValueError,OSError):
            dependencies[name]=None
    configuration_error=None
    try:
        configured,model_root,configuration_source=voice_configuration(config_root)
    except (OSError,ValueError,TypeError):
        configured=model_root=None
        configuration_source='invalid_configuration'
        configuration_error='voice_config_invalid_or_unavailable'
    voice_python=Path(configured) if configured else None
    external={'configured':bool(configured),'python_path':configured,'available':bool(voice_python and voice_python.is_absolute() and voice_python.is_file()),'dependencies':'not_probed','configuration_source':configuration_source,'configuration_error':configuration_error}
    if external['available']:
        try:
            probe=subprocess.run([voice_python,'-I','-B','-c',"import importlib.util,json; print(json.dumps({name:importlib.util.find_spec(name) is not None for name in ('pocketsphinx','faster_whisper','supertonic')}))"],capture_output=True,text=True,timeout=5,env=os.environ|{'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1'})
            if probe.returncode==0:
                external['dependencies']=json.loads(probe.stdout)
        except (OSError,ValueError,subprocess.TimeoutExpired):
            external['dependencies']='probe_unavailable'
    assets={}
    source=programs/'python/synapse_ai/voice_worker.py'
    if source.is_file():
        try:
            for node in ast.parse(source.read_text(encoding='utf-8')).body:
                if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id in ('STT_FILES','TTS_FILES') for target in node.targets):
                    key=node.targets[0].id
                    required=ast.literal_eval(node.value)
                    pack='whisper-base' if key=='STT_FILES' else 'supertonic-3'
                    assets[pack]={'configured':bool(model_root),'files_present':bool(model_root and all((Path(model_root)/pack/name).is_file() for name in required)),'integrity':'not_verified'}
        except (OSError,SyntaxError,ValueError,TypeError):
            assets={'diagnostic':'source_manifest_unavailable'}
    cache=os.environ.get('PLAYWRIGHT_BROWSERS_PATH') or (str(Path(os.environ['LOCALAPPDATA'])/'ms-playwright') if os.environ.get('LOCALAPPDATA') else None)
    cache_path=Path(cache) if cache and cache!='0' else None
    browsers=[] if not cache_path or not cache_path.is_dir() else [str(path) for pattern in ('chromium-*/chrome-win/chrome.exe','chromium-*/chrome-win64/chrome.exe','chromium_headless_shell-*/chrome-headless-shell-win64/chrome-headless-shell.exe') for path in cache_path.glob(pattern) if path.is_file()]
    voice_ready=isinstance(external['dependencies'],dict) and all(external['dependencies'].values()) and len(assets)==2 and all(item.get('files_present') for item in assets.values())
    return {'bundled_core_dependencies':dependencies,'voice':{'runtime':external,'models_path':model_root,'assets':assets,'status':'dependencies_present_not_executed' if voice_ready else 'external_setup_required','execution':'not_run'},'browser':{'playwright_module':dependencies['playwright'],'cache_path':cache,'chromium_executables':browsers,'status':'external_setup_required' if not dependencies['playwright'] or not browsers else 'dependencies_present_not_executed','execution':'not_run'},'automatic_install':'disabled'}


def diagnose(programs,config_root=None):
    results = {"version": 1, "python": {"available": sys.version_info[:2] == (3, 14), "version": sys.version.split()[0]}, "modules": {}}
    for module in ("socket", "ssl", "sqlite3", "hashlib", "urllib.request"):
        try:
            importlib.import_module(module)
            results["modules"][module] = "available"
        except ImportError:
            results["modules"][module] = "unavailable"
    results["programs"] = {name: (programs / name).is_file() for name in ("synapse-backend.exe", "synapse-maintenance.exe", "synapse-desktop-slint.exe", "synapse-image-decoder.exe", "synapse-page-analyzer.exe")}
    results["isolated_checker"] = {"available": (programs / "check-runtime/runtime/python.exe").is_file() and (programs / "check-runtime/runtime-manifest.json").is_file(), "execution": "not_run"}
    try:
        with socket.create_connection(("127.0.0.1", 1234), timeout=.4):
            results["local_provider"] = {"status": "port_reachable", "models": "not_probed", "inference": "not_run"}
    except OSError:
        results["local_provider"] = {"status": "unavailable", "models": "unknown", "inference": "not_run"}
    results["gpu"] = {"status": "unavailable", "vram_bytes": None, "measurement": "unavailable"}
    gpu = shutil.which("nvidia-smi")
    if gpu:
        try:
            measured = subprocess.run([gpu, "--query-gpu=memory.total,memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3)
            if measured.returncode == 0:
                rows = [list(map(int, line.split(","))) for line in measured.stdout.splitlines()]
                results["gpu"] = {"status": "available", "measurement": "nvidia-smi", "devices": [{"total_bytes": a*1024*1024, "used_bytes": b*1024*1024} for a,b in rows]}
        except (OSError, ValueError, subprocess.TimeoutExpired):
            results["gpu"]["status"] = "counter_unavailable"
    results["ram"] = {"total_bytes": None, "available_bytes": None, "measurement": "unavailable"}
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                        *[(name, ctypes.c_ulonglong) for name in ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]]
        memory = MemoryStatus()
        memory.length = ctypes.sizeof(memory)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            results["ram"] = {"total_bytes": memory.total, "available_bytes": memory.available, "measurement": "GlobalMemoryStatusEx"}
    results["tools"] = {name: bool(shutil.which(name)) for name in ("git", "rustc", "cargo", "pwsh")}
    # No model workload was admitted, so no claim about sufficient RAM/VRAM is made.
    results["resource_admission"] = "not_evaluated_no_workload"
    results["remote_inference"] = "disabled"
    results['optional_capabilities']=optional_capabilities(programs,config_root)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--programs", type=Path, required=True)
    parser.add_argument("--config-root", type=Path)
    args = parser.parse_args()
    result = diagnose(args.programs,args.config_root)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["python"]["available"] and all(result["programs"].values()) and result["isolated_checker"]["available"] and set(result["modules"].values()) == {"available"} else 1)
