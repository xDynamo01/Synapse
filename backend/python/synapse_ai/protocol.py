import hashlib
import json

VERSION = 1
MAX_LINE = 65536
MAX_CONTENT = 32768
MAX_MESSAGES = 64
MAX_CONTEXT_BYTES = 48000


def digest(request):
    payload = {key: request[key] for key in ("version", "request_id", "model_id", "endpoint", "messages")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def validate(request):
    if not isinstance(request, dict) or set(request) != {"version", "request_id", "model_id", "endpoint", "messages", "digest"}:
        raise ValueError("invalid_request")
    if type(request["version"]) is not int or request["version"] != VERSION:
        raise ValueError("unsupported_version")
    for key, maximum in (("request_id", 128), ("model_id", 128), ("endpoint", 1024)):
        value = request[key]
        if not isinstance(value, str) or not value.strip() or len(value.encode()) > maximum or "\x00" in value:
            raise ValueError("invalid_request")
    messages=request["messages"]
    if not isinstance(messages,list) or not 1 <= len(messages) <= MAX_MESSAGES:
        raise ValueError("invalid_request")
    for message in messages:
        if not isinstance(message,dict) or set(message)!={"role","content"} or message["role"] not in ("system","user","assistant"):
            raise ValueError("invalid_request")
        content=message["content"]
        if not isinstance(content,str) or not content.strip() or "\x00" in content or len(content.encode("utf-8"))>MAX_CONTENT:
            raise ValueError("invalid_request")
    if messages[-1]["role"]!="user" or len(json.dumps(messages,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8"))>MAX_CONTEXT_BYTES:
        raise ValueError("invalid_request")
    if request["digest"] != digest(request):
        raise ValueError("digest_mismatch")
