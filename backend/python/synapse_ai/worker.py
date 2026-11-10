import json
import sys

from .protocol import MAX_LINE, digest, validate
from .providers import ProviderError, infer


def main():
    sys.stdout.buffer.write(b'{"type":"hello","version":3}\n')
    sys.stdout.buffer.flush()
    line = sys.stdin.buffer.readline(MAX_LINE + 2)
    response = {"version": 3, "request_id": None, "digest": None, "ok": False, "content": None, "error": "invalid_request"}
    try:
        if not line.endswith(b"\n") or len(line) - 1 > MAX_LINE:
            raise ValueError("invalid_request")
        request = json.loads(line.decode("utf-8"))
        validate(request)
        response["request_id"] = request["request_id"]
        response["digest"] = digest(request)
        response["content"] = infer(request["endpoint"], request["model_id"], request["messages"], request["generation"], request["purpose"])
        response["ok"] = True
        response["error"] = None
    except ProviderError as error:
        response["error"] = str(error)
    except (ValueError, UnicodeError, json.JSONDecodeError) as error:
        response["error"] = str(error) if str(error) in ("invalid_request", "unsupported_version", "digest_mismatch") else "invalid_request"
    sys.stdout.buffer.write(json.dumps(response, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
