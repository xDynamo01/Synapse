"""One-request local browser worker. Sensitive values travel on stdin only."""
import json
import os
from pathlib import Path
import sys

from .browser_session import BrowserSession
from .browser_transport import exchange
from .browser_vault import SessionVault


def run(request, vault, transport):
    mode = request["mode"]
    origin = request["origin"]
    if mode == "store_credentials":
        handle = vault.save_credentials(origin, request["username"], request["password"])
        return {"credential_handle": handle}
    if mode == "list":
        return {"records": vault.list_records(origin)}
    if mode == "revoke":
        vault.revoke(origin, request["handle"])
        return {"revoked": True}

    handle = request["credential_handle"] if mode == "login" else request["session_handle"]
    load_record = vault.load_credentials if mode == "login" else vault.load

    def authorized_transport(origin, address, *, method, **options):
        # A different worker may revoke the local handle between network hops.
        load_record(origin, handle)
        return transport(origin, address, method=method, **options)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as runtime:
        if mode == "login":
            credentials = vault.load_credentials(origin, request["credential_handle"])
            with BrowserSession(runtime, origin, transport=authorized_transport) as session:
                outcome = session.login(page=request["page"], action=request["action"],
                                        probe=request["probe"], expected_text=request["expected_text"],
                                        **credentials)
                return {"authenticated": outcome["authenticated"],
                        "session_handle": vault.save(origin, session.storage_state())}
        if mode == "read":
            state = vault.load(origin, request["session_handle"])
            address = request["destination"]
            with BrowserSession(runtime, origin, storage_state=state, transport=authorized_transport) as session:
                result = session.read(address, allowed={address})
                updated = session.storage_state()
                if updated != state:
                    vault.refresh(origin, handle, updated)
                return result
    raise ValueError("Unknown browser worker operation")


def guarded_exchange(origin, address, *, method, **options):
    print(json.dumps({"authorize":{"destination":address,"method":method.lower()}}), flush=True)
    reply = sys.stdin.buffer.readline(65)
    if not reply.endswith(b"\n") or json.loads(reply) != {"allow": True}:
        raise ValueError("Browser network dispatch denied")
    return exchange(origin, address, method=method, **options)


def main():
    try:
        raw = sys.stdin.buffer.readline(32769)
        if not raw.endswith(b"\n") or len(raw) > 32768:
            raise ValueError("Browser worker input exceeds its size limit")
        request = json.loads(raw)
        directory = Path(os.environ["LOCALAPPDATA"]) / "Synapse" / "browser" / "vault"
        answer = run(request, SessionVault(directory), guarded_exchange)
    except Exception:
        # Request fields and provider errors may contain credentials or tokens.
        print('{"ok":false,"error":"authenticated_browser_operation_failed"}')
        return
    print(json.dumps({"ok": True, "result": answer}, ensure_ascii=True))


if __name__ == "__main__":
    main()
