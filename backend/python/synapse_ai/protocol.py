import hashlib
import json

VERSION = 4
MAX_LINE = 65536
MAX_CONTENT = 32768
MAX_MESSAGES = 64
MAX_CONTEXT_BYTES = 48000
MAX_CANDIDATE_MESSAGE = 64 * 1024
MAX_CANDIDATE_CONTEXT_BYTES = 256 * 1024
MAX_CANDIDATE_REQUEST = 260 * 1024
MAX_CANDIDATE_CONTENT = 160 * 1024
MAX_CANDIDATE_FRAME = 320 * 1024


def digest(request):
    payload = {key: request[key] for key in ("version", "request_id", "model_id", "endpoint", "messages", "generation", "purpose")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def validate(request):
    if not isinstance(request, dict) or set(request) != {"version", "request_id", "model_id", "endpoint", "messages", "generation", "purpose", "digest"}:
        raise ValueError("invalid_request")
    if type(request["version"]) is not int or request["version"] != VERSION:
        raise ValueError("unsupported_version")
    if request["purpose"] not in ("conversation", "learning", "mission_plan", "mission_generate", "mission_review"):
        raise ValueError("invalid_request")
    generation = request['generation']
    if (not isinstance(generation, dict) or set(generation) != {'max_output_tokens', 'timeout_ms', 'reasoning_effort'}
            or type(generation['max_output_tokens']) is not int or not 1 <= generation['max_output_tokens'] <= 4096
            or type(generation['timeout_ms']) is not int or not 250 <= generation['timeout_ms'] <= 120000
            or generation['reasoning_effort'] not in ('provider_default', 'none', 'low', 'medium', 'high')):
        raise ValueError('invalid_request')
    for key, maximum in (("request_id", 128), ("model_id", 128), ("endpoint", 1024)):
        value = request[key]
        if not isinstance(value, str) or not value.strip() or len(value.encode()) > maximum or "\x00" in value:
            raise ValueError("invalid_request")
    candidate_stage = request["purpose"] in ("mission_generate", "mission_review")
    message_limit = MAX_CANDIDATE_MESSAGE if candidate_stage else MAX_CONTENT
    messages=request["messages"]
    if not isinstance(messages,list) or not 1 <= len(messages) <= MAX_MESSAGES:
        raise ValueError("invalid_request")
    for message in messages:
        if not isinstance(message,dict) or set(message)!={"role","content"} or message["role"] not in ("system","user","assistant"):
            raise ValueError("invalid_request")
        content=message["content"]
        if not isinstance(content,str) or not content.strip() or "\x00" in content or len(content.encode("utf-8"))>message_limit:
            raise ValueError("invalid_request")
    context_limit = MAX_CANDIDATE_CONTEXT_BYTES if candidate_stage else MAX_CONTEXT_BYTES
    if messages[-1]["role"]!="user" or len(json.dumps(messages,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8"))>context_limit:
        raise ValueError("invalid_request")
    if request["digest"] != digest(request):
        raise ValueError("digest_mismatch")
