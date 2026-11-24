"""Operational counters only: never retain prompts, endpoints, or provider text."""
import os
import time


def rss_bytes():
    """Current worker RSS, not host capacity or model-server memory."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            class Counters(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                    (name, ctypes.c_size_t) for name in (
                        "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                        "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                        "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetCurrentProcess.restype = wintypes.HANDLE
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
            if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
                return counters.WorkingSetSize
        elif os.path.isfile("/proc/self/statm"):
            with open("/proc/self/statm", encoding="ascii") as stream:
                return int(stream.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, AttributeError, IndexError):
        pass
    return None


def new_metrics():
    return {"version": 1, "phases_ms": {}, "input_tokens": None, "output_tokens": None,
            "worker_rss_bytes": rss_bytes(), "provider_ram_bytes": None,
            "gpu_available": None, "vram_bytes": None, "inference_calls": 0,
            "remote_inference_calls": 0, "remote_cost_microunits": 0, "retries": 0,
            "residency": "unavailable", "response_cache": "disabled"}


def elapsed_ms(start):
    return max(0, int((time.monotonic() - start) * 1000))


def capture_usage(result, metrics):
    if metrics is None:
        return
    usage = result.get("usage") if isinstance(result, dict) else None
    if isinstance(usage, dict):
        for source, target in (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens")):
            value = usage.get(source)
            if type(value) is int and 0 <= value <= 2**53 - 1:
                metrics[target] = value
