"""Versioned deterministic boundary evals against the actual Core CLI artifact.

No network/provider/model is used. These scores are policy decisions, not model
quality. A fixed baseline requires zero FP/FN/leaks across all five classes.
Only aggregate diagnostics are exported; synthetic canaries stay in temp fixtures.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

CANARY = "SYNAPSE_READINESS_SECRET_CANARY_8f4c0a"


def run(binary: Path, root: Path, commands: list[dict], prefix: str) -> list[dict]:
    requests = [{"version": 1, "request_id": f"{prefix}-{i}", "command": command}
                for i, command in enumerate(commands)]
    result = subprocess.run([str(binary), "--state-dir", str(root / "state"),
                             "--workspace", str(root / "workspace")],
                            input="".join(json.dumps(r) + "\n" for r in requests),
                            capture_output=True, text=True, encoding="utf-8", timeout=25)
    if result.returncode:
        # Never copy stderr or echoed request contents into evidence.
        raise RuntimeError("Core process failed; private diagnostic content withheld")
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    if len(replies) != len(requests):
        raise RuntimeError("Core returned an unexpected response count")
    return replies


def evaluate(binary: Path, case: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="synapse-readiness-eval-") as temp:
        root = Path(temp)
        workspace = root / "workspace"
        workspace.mkdir()
        (workspace / "public.txt").write_text("public fixture\n", encoding="utf-8")
        (workspace / "secret.txt").write_text(CANARY, encoding="utf-8")
        setup = [
            {"type": "chat_create", "chat_id": c, "title": "Eval fixture", "scope": s}
            for c, s in [("chat-a", "project:a"), ("chat-b", "project:b")]]
        setup += [{"type": "memory_put", "scope": "project:a", "key": "constraint",
                   "kind": "constraint", "content": CANARY, "expected_revision": 0,
                   "status": "active", "provenance": {"source_type": "eval",
                   "source_id": "fixture", "evidence": "synthetic only"}},
                  {"type": "mission_propose", "mission_id": "read-a", "contract": {
                   "version": 1, "scope": "project:a", "objective": "Read exact public fixture",
                   "actions": ["workspace_read"], "resources": ["public.txt"],
                   "rollback": "none"}}]
        replies = run(binary, root, setup, "setup")
        if not all(reply.get("ok") for reply in replies):
            raise RuntimeError("Eval setup rejected; no score may be reported")
        approved = run(binary, root, [{"type": "mission_approve", "mission_id": "read-a",
                     "contract_digest": replies[-1]["result"]["contract_digest"]}], "approval")
        if not approved[0].get("ok"):
            raise RuntimeError("Eval approval setup rejected")
        if case.get("revoke"):
            run(binary, root, [{"type": "mission_revoke", "mission_id": "read-a",
                               "reason": "eval revocation"}], "revoke")
        started = time.perf_counter()
        reply = run(binary, root, [case["command"]], "case")[0]
        output = reply.get("result") or {}
        observed = {"ok": reply.get("ok") is True,
                    "mission_route": output.get("route") == "mission",
                    "clarification": output.get("status") == "needs_clarification"}[case["observe"]]
        leak = case.get("no_canary", False) and CANARY in json.dumps(reply)
        return {"id": case["id"], "class": case["class"], "label": case["label"],
                "expected": case["expected"], "observed": observed,
                "pass": observed == case["expected"] and not leak, "canary_leak": bool(leak),
                "latency_ms": round((time.perf_counter() - started) * 1000, 3)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=Path(__file__).with_name("evals-v1.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    artifact_sha256 = hashlib.sha256(binary.read_bytes()).hexdigest()
    dataset_bytes = args.dataset.read_bytes()
    dataset = json.loads(dataset_bytes)
    rows = [evaluate(binary, case) for case in dataset["cases"]]
    if hashlib.sha256(binary.read_bytes()).hexdigest() != artifact_sha256:
        raise RuntimeError("Core artifact changed during eval; discard the run and repeat")
    classes = {}
    for name in sorted({row["class"] for row in rows}):
        subset = [r for r in rows if r["class"] == name]
        positives = sum(r["expected"] for r in subset)
        negatives = len(subset) - positives
        fp = sum(r["observed"] and not r["expected"] for r in subset)
        fn = sum(not r["observed"] and r["expected"] for r in subset)
        classes[name] = {"cases": len(subset), "positive_denominator": positives,
                         "negative_denominator": negatives, "false_positives": fp,
                         "false_negatives": fn, "false_positive_rate": fp / negatives if negatives else None,
                         "false_negative_rate": fn / positives if positives else None}
    passed = all(row["pass"] for row in rows) and len(rows) == dataset["baseline"]["expected_cases"]
    report = {"version": 1, "dataset": dataset["name"], "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
              "artifact_sha256": artifact_sha256,
              "configuration": "Windows local Core; no provider/model; disposable state",
              "baseline": dataset["baseline"], "thresholds": dataset["thresholds"],
              "model_evals": "NOT RUN", "distribution_acceptance": "NOT RUN",
              "status": "PASS" if passed else "FAIL", "classes": classes, "cases": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "cases": len(rows), "classes": classes}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
