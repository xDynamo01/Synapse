import json
import socket
import urllib.error
import urllib.parse
import urllib.request

from .protocol import MAX_CONTENT

MAX_PROVIDER_BYTES = 131072

# Static schema only: model output is still independently validated by Core.
LEARNING_FORMAT = {"type": "json_schema", "json_schema": {"name": "memory_candidates", "strict": True, "schema": {
    "type": "object", "additionalProperties": False, "required": ["candidates"],
    "properties": {"candidates": {"type": "array", "maxItems": 8, "items": {
        "type": "object", "additionalProperties": False, "required": ["key", "kind", "content"],
        "properties": {"key": {"type": "string", "maxLength": 64}, "kind": {"type": "string", "enum": ["fact", "constraint", "decision"]}, "content": {"type": "string", "maxLength": 512}}
    }}}
}}}


class ProviderError(Exception):
    pass


def validate_endpoint(endpoint):
    try:
        parsed = urllib.parse.urlsplit(endpoint)
        port = parsed.port
    except ValueError:
        raise ProviderError("invalid_endpoint") from None
    if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "[::1]", "::1")
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/v1") or not port
            or parsed.netloc not in (f"{parsed.hostname}:{port}", f"[{parsed.hostname}]:{port}")):
        raise ProviderError("invalid_endpoint")
    return f"http://{parsed.netloc}/v1"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError("provider_redirect")


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def _json(url, payload=None, timeout=10):
    data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {}, method="POST" if data else "GET")
    try:
        with OPENER.open(request, timeout=timeout) as response:
            raw = response.read(MAX_PROVIDER_BYTES + 1)
            if len(raw) > MAX_PROVIDER_BYTES:
                raise ProviderError("provider_malformed")
            return json.loads(raw.decode("utf-8"))
    except (socket.timeout, TimeoutError):
        raise ProviderError("provider_timeout") from None
    except urllib.error.HTTPError as error:
        if error.code in (404, 422, 503):
            raise ProviderError("model_unavailable") from None
        raise ProviderError("provider_error") from None
    except (urllib.error.URLError, OSError):
        raise ProviderError("provider_unavailable") from None
    except (UnicodeError, json.JSONDecodeError):
        raise ProviderError("provider_malformed") from None


def infer(endpoint, model_id, messages, generation, purpose="conversation"):
    base = validate_endpoint(endpoint)
    timeout = generation['timeout_ms'] / 1000
    models = _json(base + "/models", timeout=timeout)
    if not isinstance(models, dict) or not isinstance(models.get("data"), list):
        raise ProviderError("provider_malformed")
    if not any(isinstance(item, dict) and item.get("id") == model_id for item in models["data"]):
        raise ProviderError("model_unavailable")
    payload = {"model": model_id, "messages": messages, "stream": False, "max_tokens": generation['max_output_tokens']}
    if purpose == "learning":
        payload["response_format"] = LEARNING_FORMAT
    if generation['reasoning_effort'] != 'provider_default':
        payload['reasoning_effort'] = generation['reasoning_effort']
    result = _json(base + "/chat/completions", payload, timeout=timeout)
    try:
        choices = result["choices"]
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError()
        message = choices[0]["message"]
        if message.get("tool_calls") or message.get("function_call") or message.get("role") != "assistant":
            raise ValueError()
        content = message["content"]
        if not isinstance(content, str) or not content.strip() or len(content.encode()) > MAX_CONTENT:
            raise ValueError()
        return content
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise ProviderError("provider_malformed") from None
