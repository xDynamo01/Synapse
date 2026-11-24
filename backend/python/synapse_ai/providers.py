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

from .model_ownership import OwnershipError, ownership
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

PLANNED_TASK_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["task_id", "objective", "dependencies", "priority", "artifacts"],
    "properties": {
        "task_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "objective": {"type": "string", "minLength": 1, "maxLength": 512},
        "dependencies": {"type": "array", "maxItems": 7, "uniqueItems": True,
                         "items": {"type": "string", "minLength": 1, "maxLength": 128}},
        "priority": {"type": "integer", "minimum": 0, "maximum": 100},
        "artifacts": {"type": "array", "minItems": 1, "maxItems": 16, "uniqueItems": True,
                      "items": ARTIFACT_PATH_SCHEMA},
    },
}


MISSION_PLAN_FORMAT = {"type": "json_schema", "json_schema": {"name": "mission_plan", "strict": True, "schema": {
    "type": "object", "additionalProperties": False, "required": ["summary", "artifacts", "checks", "tasks"],
    "properties": {
        "summary": {"type": "string", "minLength": 1, "maxLength": 2048},
        "artifacts": {"type": "array", "minItems": 1, "maxItems": 16, "uniqueItems": True, "items": {
            "type": "object", "additionalProperties": False, "required": ["path", "purpose"],
            "properties": {
                "path": ARTIFACT_PATH_SCHEMA,
                "purpose": {"type": "string", "minLength": 1, "maxLength": 512}
            }}},
        "checks": {"type": "array", "minItems": 1, "maxItems": 8, "uniqueItems": True,
                   "items": {"anyOf": [_check_schema(kind, suffix) for kind, suffix in CHECK_RECIPES.items()]}},
        # Match Core's planner::validate: one coherent unit uses []; a
        # decomposed mission requires 2..8 tasks. Never offer a one-task shape.
        "tasks": {"anyOf": [
            {"type": "array", "maxItems": 0, "items": PLANNED_TASK_SCHEMA},
            {"type": "array", "minItems": 2, "maxItems": 8, "items": PLANNED_TASK_SCHEMA},
        ]}
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


def _catalog_instances(catalog):
    try:
        entries = catalog["models"]
        by_key = {entry["key"]: entry for entry in entries}
        resident = {}
        for entry in entries:
            for instance in entry["loaded_instances"]:
                identifier = instance["id"]
                if not isinstance(identifier, str) or identifier in resident:
                    raise ValueError
                resident[identifier] = entry["key"]
        return by_key, resident
    except (KeyError, TypeError, ValueError):
        raise ProviderError("provider_malformed") from None


def _reconcile_ownership(journal, api, catalog, timeout):
    record = journal.read()
    if record is None:
        return catalog
    _, resident = _catalog_instances(catalog)
    instance = record["instance"]
    if instance not in resident:
        if record["phase"] == "pending":
            # The provider may still complete a submitted load after the client died.
            raise ProviderError("model_release_uncertain")
        journal.clear(recovered=record)
        return catalog
    if record["kind"] != "cli" or resident[instance] != record["model"]:
        # REST identifiers can be reused after an operator reload. Never infer
        # ownership of a stale REST identifier from a catalogue entry.
        raise ProviderError("model_release_uncertain")
    return _release_recorded_model(journal, api, instance, timeout, recovered=record)


def _release_recorded_model(journal, api, instance, timeout=2, recovered=None):
    try:
        _release_model(api, instance)
        catalog = _json(api, timeout=min(timeout, 2))
        _, resident = _catalog_instances(catalog)
        if instance in resident:
            raise ProviderError("model_release_uncertain")
    except ProviderError:
        raise ProviderError("model_release_uncertain") from None
    journal.clear(recovered=recovered)
    return catalog


@contextmanager
def _cli_model_instance(cli, api, model_id, context_length, timeout, journal=None):
    if (not os.path.isabs(cli) or not os.path.isfile(cli) or model_id.startswith("-")):
        raise ProviderError("invalid_endpoint")
    instance = journal.reserve_cli(model_id) if journal else "synapse-" + uuid.uuid4().hex
    acquired = False
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
        except OSError:
            if journal:
                journal.clear()
            raise ProviderError("model_unavailable") from None
        except subprocess.CalledProcessError:
            raise ProviderError("model_unavailable") from None
        _, resident = _catalog_instances(_json(api, timeout=2))
        if resident.get(instance) != model_id:
            raise ProviderError("model_unavailable")
        acquired = True
        if journal:
            journal.write(model_id, "cli", instance, "acquired")
        yield instance
    except ProviderError:
        if journal and not acquired and journal.read() is not None:
            raise ProviderError("model_release_uncertain") from None
        raise
    finally:
        if journal:
            if acquired:
                _release_recorded_model(journal, api, instance)
        else:
            # Legacy workers rely on the provider TTL if cleanup cannot connect.
            # A cleanup error after successful load remains visible.
            try:
                _release_model(api, instance)
            except ProviderError:
                if acquired:
                    raise


@contextmanager
def model_instance(base, model_id, timeout, metrics=None):
    if os.environ.get("SYNAPSE_MANAGE_LOCAL_MODELS") != "1":
        if metrics is not None:
            metrics["residency"] = "management_disabled"
        yield model_id
        return
    try:
        with ownership(base) as journal:
            with _managed_model_instance(base, model_id, timeout, journal, metrics=metrics) as instance:
                yield instance
    except OwnershipError as error:
        raise ProviderError(str(error)) from None


@contextmanager
def _managed_model_instance(base, model_id, timeout, journal, metrics=None):
    api = base.removesuffix("/v1") + "/api/v1/models"
    start = time.monotonic()
    catalog = _json(api, timeout=min(timeout, 5))
    if journal:
        catalog = _reconcile_ownership(journal, api, catalog, timeout)
    by_key, resident = _catalog_instances(catalog)
    target = by_key.get(model_id)
    if model_id in resident:
        if metrics is not None:
            metrics["residency"] = "reused_operator_instance"
        yield model_id
        return
    if target is None:
        raise ProviderError("model_unavailable")
    if target["loaded_instances"]:
        if metrics is not None:
            metrics["residency"] = "reused_operator_instance"
        yield target["loaded_instances"][0]["id"]
        return
    if resident:
        raise ProviderError("model_capacity_busy")
    try:
        context_length = min(32768, target["max_context_length"])
    except (KeyError, TypeError, ValueError):
        raise ProviderError("provider_malformed") from None
    remaining = timeout - (time.monotonic() - start)
    if remaining <= 0:
        raise ProviderError("provider_timeout")
    cli = os.environ.get("SYNAPSE_LMS_EXECUTABLE")
    if cli:
        # The CLI targets the local service, whose REST port is fixed for this integration.
        if base != "http://127.0.0.1:1234/v1":
            raise ProviderError("invalid_endpoint")
        with _cli_model_instance(cli, api, model_id, context_length, remaining, journal) as instance:
            if metrics is not None:
                metrics["residency"] = "acquired_owned_instance"
            yield instance
        return
    if journal:
        journal.write(model_id, "rest", None, "pending")
    try:
        loaded = _json(api + "/load", {"model": model_id, "context_length": context_length,
                                      "offload_kv_cache_to_gpu": False}, timeout=remaining)
        if not isinstance(loaded, dict) or not loaded.get("instance_id") or not isinstance(loaded["instance_id"], str):
            raise ProviderError("provider_malformed")
    except ProviderError:
        if journal:
            raise ProviderError("model_release_uncertain") from None
        raise
    instance = loaded["instance_id"]
    if metrics is not None:
        metrics["residency"] = "acquired_owned_instance"
    # The exact response ID belongs to this live acquisition. It cannot prove
    # ownership of a potentially replaced REST instance after a process restart.
    try:
        if journal:
            journal.write(model_id, "rest", instance, "acquired")
        yield instance
    finally:
        if journal:
            _release_recorded_model(journal, api, instance)
        else:
            _release_model(api, instance)


def infer(endpoint, model_id, messages, generation, purpose="conversation", metrics=None):
    from .metrics import elapsed_ms
    base = validate_endpoint(endpoint)
    timeout = generation['timeout_ms'] / 1000
    started = time.monotonic()
    try:
        with model_instance(base, model_id, timeout, metrics=metrics) as instance:
            if metrics is not None:
                metrics["phases_ms"]["model_acquisition"] = elapsed_ms(started)
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise ProviderError("provider_timeout")
            inference_start = time.monotonic()
            try:
                return _infer(base, instance, messages, generation, purpose, remaining, metrics=metrics)
            finally:
                if metrics is not None:
                    metrics["phases_ms"]["inference"] = elapsed_ms(inference_start)
                cleanup_start = time.monotonic()
    finally:
        if metrics is not None:
            metrics["phases_ms"]["provider_total"] = elapsed_ms(started)
            if "model_acquisition" not in metrics["phases_ms"]:
                metrics["phases_ms"]["model_acquisition"] = elapsed_ms(started)
            if "cleanup_start" in locals():
                metrics["phases_ms"]["model_cleanup"] = elapsed_ms(cleanup_start)


def _infer(base, model_id, messages, generation, purpose, timeout, metrics=None):
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
    if metrics is not None:
        metrics["inference_calls"] += 1
    result = _json(base + "/chat/completions", payload, timeout=remaining, response_limit=response_limit)
    from .metrics import capture_usage
    capture_usage(result, metrics)
    try:
        choices = result["choices"]
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError()
        if choices[0].get("finish_reason") == "length":
            raise ProviderError("provider_output_limit")
        message = choices[0]["message"]
        if message.get("tool_calls") or message.get("function_call") or message.get("role") != "assistant":
            raise ValueError()
        content = message["content"]
        if not isinstance(content, str) or not content.strip() or len(content.encode()) > content_limit:
            raise ValueError()
        return content
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise ProviderError("provider_malformed") from None
