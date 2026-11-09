import hashlib
import json

VERSION = 1
MAX_LINE = 65536
MAX_CONTENT = 32768


def digest(request):
    payload = {key: request[key] for key in ("version", "request_id", "model_id", "endpoint", "prompt")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def validate(request):
    if not isinstance(request, dict) or set(request) != {"version", "request_id", "model_id", "endpoint", "prompt", "digest"}:
        raise ValueError("invalid_request")
    if type(request["version"]) is not int or request["version"] != VERSION:
        raise ValueError("unsupported_version")
    for key, maximum in (("request_id", 128), ("model_id", 128), ("endpoint", 1024), ("prompt", MAX_CONTENT)):
        value = request[key]
        if not isinstance(value, str) or not value.strip() or len(value.encode()) > maximum or "\x00" in value:
            raise ValueError("invalid_request")
    if request["digest"] != digest(request):
        raise ValueError("digest_mismatch")
