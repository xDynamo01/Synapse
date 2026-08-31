from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import threading
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

from synapse.main import app

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8717
HANDSHAKE_SCHEMA_VERSION = 1
HANDSHAKE_RELATIVE_PATH = Path("runtime/backend-handshake.json")


@dataclass(frozen=True)
class BackendHandshake:
    schema_version: int
    host: str
    port: int
    pid: int
    token: str
    started_at: str
    version: str


def log_bootstrap(message: str) -> None:
    timestamp = datetime.now(UTC).isoformat(timespec="milliseconds")
    print(f"[{timestamp}] {message}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synapse desktop backend sidecar")
    parser.add_argument("--host", default=os.environ.get("SYNAPSE_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("SYNAPSE_PORT", str(DEFAULT_PORT))),
    )
    return parser


def bind_backend_socket(host: str, requested_port: int) -> socket.socket:
    backend_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    backend_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        backend_socket.bind((host, requested_port))
        backend_socket.listen(2048)
        backend_socket.set_inheritable(True)
        return backend_socket
    except BaseException:
        backend_socket.close()
        raise


def write_handshake_atomic(path: Path, handshake: BackendHandshake) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{handshake.pid}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(asdict(handshake), handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def remove_owned_handshake(path: Path, pid: int, token: str) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("pid") == pid and payload.get("token") == token:
            path.unlink(missing_ok=True)
    except (OSError, ValueError, TypeError):
        return


def backend_is_ready(host: str, port: int) -> bool:
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    try:
        with urlopen(f"http://{probe_host}:{port}/api/sidecar/startup-ready", timeout=1.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return (
                response.status == 200
                and response.headers.get("X-Synapse-Service") == "synapse-backend"
                and payload.get("schema") == "synapse-sidecar-startup-ready-v1"
                and payload.get("ready") is True
                and payload.get("startup_status") in {"ready", "degraded"}
            )
    except (OSError, URLError, ValueError, TypeError):
        return False


def publish_when_ready(
    server: uvicorn.Server,
    handshake_path: Path,
    handshake: BackendHandshake,
    stop_event: threading.Event,
    timeout_seconds: float = 60.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not stop_event.is_set() and time.monotonic() < deadline:
        if server.started and backend_is_ready(handshake.host, handshake.port):
            try:
                write_handshake_atomic(handshake_path, handshake)
                log_bootstrap(f"Handshake escrito em: {handshake_path}")
            except BaseException as error:
                log_bootstrap(f"Falha ao escrever handshake em {handshake_path}: {error!r}")
                server.should_exit = True
            return
        stop_event.wait(0.1)
    if not stop_event.is_set():
        log_bootstrap(
            f"Backend não ficou pronto para publicar o handshake em {timeout_seconds:g} segundos"
        )
        server.should_exit = True


def main(arguments: Sequence[str] | None = None) -> None:
    options = build_parser().parse_args(arguments)
    data_dir = Path(os.environ.get("SYNAPSE_DATA_DIR", "./data")).resolve()
    handshake_path = (data_dir / HANDSHAKE_RELATIVE_PATH).resolve()
    token = os.environ.get("SYNAPSE_LAUNCH_TOKEN") or secrets.token_urlsafe(32)

    log_bootstrap(f"DATA_DIR resolvido: {data_dir}")
    log_bootstrap(f"Caminho do handshake resolvido: {handshake_path}")
    if options.port == 0:
        log_bootstrap("Porta dinâmica solicitada")
    log_bootstrap(f"Iniciando bind em {options.host}:{options.port}")
    try:
        backend_socket = bind_backend_socket(options.host, options.port)
    except BaseException as error:
        log_bootstrap(f"Falha ao abrir socket em {options.host}:{options.port}: {error!r}")
        raise

    actual_port = int(backend_socket.getsockname()[1])
    log_bootstrap("Bind concluído")
    log_bootstrap(f"Porta real obtida: {actual_port}")
    handshake = BackendHandshake(
        schema_version=HANDSHAKE_SCHEMA_VERSION,
        host=options.host,
        port=actual_port,
        pid=os.getpid(),
        token=token,
        started_at=datetime.now(UTC).isoformat(),
        version=str(app.version),
    )
    stop_event = threading.Event()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=options.host,
            port=actual_port,
            log_level=os.environ.get("SYNAPSE_LOG_LEVEL", "info"),
        )
    )
    log_bootstrap("uvicorn.Server criado")
    publisher = threading.Thread(
        target=publish_when_ready,
        args=(server, handshake_path, handshake, stop_event),
        name="synapse-handshake-publisher",
        daemon=True,
    )
    log_bootstrap("Aguardando ready signal para escrever handshake")
    publisher.start()
    try:
        server.run(sockets=[backend_socket])
    finally:
        stop_event.set()
        publisher.join(timeout=1.0)
        backend_socket.close()
        remove_owned_handshake(handshake_path, handshake.pid, handshake.token)


if __name__ == "__main__":
    main()
