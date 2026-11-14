from copy import deepcopy
from contextlib import contextmanager
import json
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .protocol import MAX_CANDIDATE_CONTENT, MAX_CANDIDATE_FRAME, MAX_CONTENT

MAX_PROVIDER_BYTES = 131072

# Static schema only: model output is still independently validated by Core.
LEARNING_FORMAT = {"type": "json_schema", "json_schema": {"name": "memory_candidates", "strict": True, "schema": {
    "type": "object", "additionalProperties": False, "required": ["candidates"],
    "properties": {"candidates": {"type": "array", "maxItems": 8, "items": {
        "type": "object", "additionalProperties": False, "required": ["key", "kind", "content"],
        "properties": {"key": {"type": "string", "maxLength": 64}, "kind": {"type": "string", "enum": ["fact", "constraint", "decision"]}, "content": {"type": "string", "maxLength": 512}}
    }}}
}}}


# Fixed schema, never supplied or extended by a caller/model. Core enforces UTF-8
# byte budgets and cross-array constraints (exact entrypoints and case collisions).
SAFE_COMPONENT = r'(?![. ])(?!.*\.\.)(?!.*[/\\:<>"|?*])(?!(?:[Cc][Oo][Nn]|[Pp][Rr][Nn]|[Aa][Uu][Xx]|[Nn][Uu][Ll]|[Cc][Oo][Mm][1-9]|[Ll][Pp][Tt][1-9]|[Cc][Ll][Oo][Cc][Kk]\$|[Cc][Oo][Nn][Ii][Nn]\$|[Cc][Oo][Nn][Oo][Uu][Tt]\$) *(?:\.|$))[ -~]+'


def _check_schema(kind, suffix):
    return {"type": "object", "additionalProperties": False, "required": ["kind", "entrypoint"],
            "properties": {"kind": {"type": "string", "enum": [kind]},
                           "entrypoint": {"type": "string", "minLength": 1, "maxLength": 128,
                                          "pattern": '^' + SAFE_COMPONENT + r'\.' + suffix + '$'}}}


ARTIFACT_PATH_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 128,
                        "pattern": '^' + SAFE_COMPONENT + r'\.(?:rs|py|md|txt|toml|json|csv|svg|vtt)$'}


CHECK_RECIPES = {
    "python_unittest": "py", "rust_test": "rs", "python_compile": "py",
    "json_validate": "json", "game_level_validate": "json", "toml_validate": "toml", "python_manifest_validate": "toml", "csv_validate": "csv",
    "svg_validate": "svg", "markdown_validate": "md", "webvtt_validate": "vtt",
}


MISSION_PLAN_FORMAT = {"type": "json_schema", "json_schema": {"name": "mission_plan", "strict": True, "schema": {
    "type": "object", "additionalProperties": False, "required": ["summary", "artifacts", "checks"],
    "properties": {
        "summary": {"type": "string", "minLength": 1, "maxLength": 2048},
        "artifacts": {"type": "array", "minItems": 1, "maxItems": 16, "uniqueItems": True, "items": {
            "type": "object", "additionalProperties": False, "required": ["path", "purpose"],
            "properties": {
                "path": ARTIFACT_PATH_SCHEMA,
                "purpose": {"type": "string", "minLength": 1, "maxLength": 512}
            }}},
        "checks": {"type": "array", "minItems": 1, "maxItems": 8, "uniqueItems": True,
                   "items": {"anyOf": [_check_schema(kind, suffix) for kind, suffix in CHECK_RECIPES.items()]}}
    }
}}}


MISSION_GENERATE_FORMAT = {"type": "json_schema", "json_schema": {"name": "mission_generate", "strict": True, "schema": {
    "type": "object", "additionalProperties": False, "required": ["artifacts"],
    "properties": {"artifacts": {"type": "array", "minItems": 1, "maxItems": 16, "items": {
        "type": "object", "additionalProperties": False, "required": ["path", "content"],
        "properties": {
            "path": ARTIFACT_PATH_SCHEMA,
            "content": {"type": "string", "maxLength": 8192}
        }
    }}}
}}}

MISSION_REVIEW_FORMAT = {"type": "json_schema", "json_schema": {"name": "mission_review", "strict": True, "schema": {
    "type": "object", "additionalProperties": False, "required": ["approved", "reason"],
    "properties": {
        "approved": {"type": "boolean"},
        "reason": {"type": "string", "minLength": 1, "maxLength": 2048}
    }
}}}

TRANSLATION_FORMAT = {"type": "json_schema", "json_schema": {"name": "translation", "strict": True, "schema": {
    "type": "object", "additionalProperties": False, "required": ["translation"],
    "properties": {"translation": {"type": "string", "minLength": 1, "maxLength": 8192}}
}}}

RESPONSE_FORMATS = {
    "translation": TRANSLATION_FORMAT,
    "learning": LEARNING_FORMAT,
    "mission_plan": MISSION_PLAN_FORMAT,
    "mission_review": MISSION_REVIEW_FORMAT,
}


class ProviderError(Exception):
    pass


def _mission_generate_format(messages):
    # Only Core's approved artifact metadata specializes this fixed template.
    try:
        planned = json.loads(messages[-1]["content"])["artifacts"]
        if not isinstance(planned, list) or not 1 <= len(planned) <= 16:
            raise ValueError()
        paths = [artifact["path"] for artifact in planned]
        if any(not isinstance(path, str) or len(path) > 128
               or not re.fullmatch(ARTIFACT_PATH_SCHEMA["pattern"], path)
               for path in paths):
            raise ValueError()
        if len(set(path.lower() for path in paths)) != len(paths):
            raise ValueError()
    except (IndexError, KeyError, TypeError, ValueError):
        raise ProviderError("provider_malformed") from None
    response_format = deepcopy(MISSION_GENERATE_FORMAT)
    array = response_format["json_schema"]["schema"]["properties"]["artifacts"]
    array["minItems"] = array["maxItems"] = len(paths)
    array["items"]["properties"]["path"] = {"type": "string", "enum": paths}
    return response_format


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


def _json(url, payload=None, timeout=10, response_limit=MAX_PROVIDER_BYTES):
    data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {}, method="POST" if data else "GET")
    try:
        with OPENER.open(request, timeout=timeout) as response:
            raw = response.read(response_limit + 1)
            if len(raw) > response_limit:
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


def _release_model(api, instance):
    payload = {"instance_id": instance}
    try:
        _json(api + "/unload", payload, timeout=2)
    except ProviderError as error:
        if str(error) not in {"provider_timeout", "provider_unavailable", "model_unavailable"}:
            raise
        # Verify absence before treating an ambiguous unload as complete.
        catalog = _json(api, timeout=1)
        try:
            resident = any(
                loaded["id"] == instance
                for model in catalog["models"]
                for loaded in model["loaded_instances"]
            )
        except (KeyError, TypeError):
            raise ProviderError("provider_malformed") from None
        if resident:
            _json(api + "/unload", payload, timeout=2)


@contextmanager
def _cli_model_instance(cli, api, model_id, context_length, timeout):
    if (not os.path.isabs(cli) or not os.path.isfile(cli) or model_id.startswith("-")):
        raise ProviderError("invalid_endpoint")
    instance = "synapse-" + uuid.uuid4().hex
    try:
        try:
            subprocess.run(
                [cli, "load", "--identifier", instance, "--context-length", str(context_length),
                 "--ttl", "180", "--yes", "--", model_id],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=timeout, check=True,
            )
        except subprocess.TimeoutExpired:
            raise ProviderError("provider_timeout") from None
        except (OSError, subprocess.CalledProcessError):
            raise ProviderError("model_unavailable") from None
        catalog = _json(api, timeout=2)
        try:
            loaded = any(item["id"] == instance for model in catalog["models"]
                         if model["key"] == model_id for item in model["loaded_instances"])
        except (KeyError, TypeError):
            raise ProviderError("provider_malformed") from None
        if not loaded:
            raise ProviderError("model_unavailable")
        yield instance
    except BaseException:
        try:
            _release_model(api, instance)
        except ProviderError:
            # The server-side TTL remains in effect if cleanup cannot connect.
            pass
        raise
    else:
        _release_model(api, instance)


@contextmanager
def model_instance(base, model_id, timeout):
    if os.environ.get("SYNAPSE_MANAGE_LOCAL_MODELS") != "1":
        yield model_id
        return
    api = base.removesuffix("/v1") + "/api/v1/models"
    start = time.monotonic()
    catalog = _json(api, timeout=min(timeout, 5))
    try:
        entries = catalog["models"]
        by_key = {entry["key"]: entry for entry in entries}
        instances = [instance["id"] for entry in entries for instance in entry["loaded_instances"]]
        target = by_key.get(model_id)
        if target is not None:
            context_length = min(32768, target["max_context_length"])
            target_instances = target["loaded_instances"]
    except (KeyError, TypeError, ValueError):
        raise ProviderError("provider_malformed") from None
    if model_id in instances:
        yield model_id
        return
    if target is None:
        raise ProviderError("model_unavailable")
    if target_instances:
        yield target_instances[0]["id"]
        return
    if instances:
        raise ProviderError("model_capacity_busy")
    remaining = timeout - (time.monotonic() - start)
    if remaining <= 0:
        raise ProviderError("provider_timeout")
    cli = os.environ.get("SYNAPSE_LMS_EXECUTABLE")
    if cli:
        # The CLI targets the local service, whose REST port is fixed for this integration.
        if base != "http://127.0.0.1:1234/v1":
            raise ProviderError("invalid_endpoint")
        with _cli_model_instance(cli, api, model_id, context_length, remaining) as instance:
            yield instance
        return
    loaded = _json(api + "/load", {"model": model_id, "context_length": context_length,
                                  "offload_kv_cache_to_gpu": False}, timeout=remaining)
    if not isinstance(loaded, dict) or not isinstance(loaded.get("instance_id"), str):
        raise ProviderError("provider_malformed")
    instance = loaded["instance_id"]
    try:
        yield instance
    finally:
        _release_model(api, instance)


def infer(endpoint, model_id, messages, generation, purpose="conversation"):
    base = validate_endpoint(endpoint)
    timeout = generation['timeout_ms'] / 1000
    started = time.monotonic()
    with model_instance(base, model_id, timeout) as instance:
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise ProviderError("provider_timeout")
        return _infer(base, instance, messages, generation, purpose, remaining)


def _infer(base, model_id, messages, generation, purpose, timeout):
    start = time.monotonic()
    models = _json(base + "/models", timeout=timeout)
    if not isinstance(models, dict) or not isinstance(models.get("data"), list):
        raise ProviderError("provider_malformed")
    if not any(isinstance(item, dict) and item.get("id") == model_id for item in models["data"]):
        raise ProviderError("model_unavailable")
    payload = {"model": model_id, "messages": messages, "stream": False, "max_tokens": generation['max_output_tokens']}
    if purpose == "mission_generate":
        payload["response_format"] = _mission_generate_format(messages)
    elif purpose in RESPONSE_FORMATS:
        payload["response_format"] = RESPONSE_FORMATS[purpose]
    if generation['reasoning_effort'] != 'provider_default':
        payload['reasoning_effort'] = generation['reasoning_effort']
    generation_response = purpose == "mission_generate"
    response_limit = MAX_CANDIDATE_FRAME if generation_response else MAX_PROVIDER_BYTES
    content_limit = MAX_CANDIDATE_CONTENT if generation_response else MAX_CONTENT
    remaining = timeout - (time.monotonic() - start)
    if remaining <= 0:
        raise ProviderError("provider_timeout")
    result = _json(base + "/chat/completions", payload, timeout=remaining, response_limit=response_limit)
    try:
        choices = result["choices"]
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError()
        message = choices[0]["message"]
        if message.get("tool_calls") or message.get("function_call") or message.get("role") != "assistant":
            raise ValueError()
        content = message["content"]
        if not isinstance(content, str) or not content.strip() or len(content.encode()) > content_limit:
            raise ValueError()
        return content
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise ProviderError("provider_malformed") from None
