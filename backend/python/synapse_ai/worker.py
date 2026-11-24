import json
import sys
import time

from .protocol import MAX_LINE, MAX_CANDIDATE_REQUEST, digest, validate
from .providers import ProviderError, infer
from .metrics import new_metrics, elapsed_ms, rss_bytes


def main():
    # Old Core launches without options and requires this exact v4 greeting.
    # New Core explicitly opts in; old workers safely ignore that CLI option.
    protocol_five = "--protocol-version=5" in sys.argv[1:]
    hello = (b'{"type":"hello","version":5,"supported_versions":[4,5],"capabilities":["operational_metrics_v1"]}\n'
             if protocol_five else b'{"type":"hello","version":4}\n')
    sys.stdout.buffer.write(hello)
    sys.stdout.buffer.flush()
    line = sys.stdin.buffer.readline(MAX_CANDIDATE_REQUEST + 2)
    response = {"version": 4, "request_id": None, "digest": None, "ok": False, "content": None, "error": "invalid_request"}
    metrics = new_metrics()
    started = time.monotonic()
    try:
        if not line.endswith(b"\n") or len(line) - 1 > MAX_CANDIDATE_REQUEST:
            raise ValueError("invalid_request")
        request = json.loads(line.decode("utf-8"))
        if len(line) - 1 > MAX_LINE and (not isinstance(request, dict) or request.get("purpose") not in ("mission_generate", "mission_review")):
            raise ValueError("invalid_request")
        validate(request)
        if request["version"] == 5 and not protocol_five:
            raise ValueError("unsupported_version")
        response["version"] = request["version"]
        if request["version"] == 5:
            response["metrics"] = metrics
        response["request_id"] = request["request_id"]
        response["digest"] = digest(request)
        metrics["phases_ms"]["validation"] = elapsed_ms(started)
        response["content"] = infer(request["endpoint"], request["model_id"], request["messages"], request["generation"], request["purpose"], metrics=metrics)
        response["ok"] = True
        response["error"] = None
    except ProviderError as error:
        response["error"] = str(error)
    except (ValueError, UnicodeError, json.JSONDecodeError) as error:
        response["error"] = str(error) if str(error) in ("invalid_request", "unsupported_version", "digest_mismatch") else "invalid_request"
    metrics["phases_ms"]["worker_total"] = elapsed_ms(started)
    metrics["worker_rss_bytes"] = rss_bytes()
    sys.stdout.buffer.write(json.dumps(response, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
