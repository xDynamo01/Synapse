"""Generate only from the local versioned schema, using locked grpcio-tools."""
from pathlib import Path
from grpc_tools import protoc

root = Path(__file__).resolve().parents[1]
out = root / "generated" / "python"
out.mkdir(parents=True, exist_ok=True)
raise SystemExit(protoc.main([
    "grpc_tools.protoc", f"-I{root / 'proto'}", f"--python_out={out}",
    f"--grpc_python_out={out}", str(root / "proto/synapse/foundation/v1/lifecycle.proto"),
]))
