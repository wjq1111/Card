from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PROTO_DIR = ROOT / "src" / "proto"
OUT_DIR = ROOT / "src" / "proto_gen"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"-I{PROTO_DIR}",
            f"--python_out={OUT_DIR}",
            f"--grpc_python_out={OUT_DIR}",
            str(PROTO_DIR / "poker.proto"),
        ]
    )
    init_file = OUT_DIR / "__init__.py"
    init_file.touch()
    grpc_file = OUT_DIR / "poker_pb2_grpc.py"
    grpc_file.write_text(
        grpc_file.read_text(encoding="utf-8").replace(
            "import poker_pb2 as poker__pb2",
            "from proto_gen import poker_pb2 as poker__pb2",
        ),
        encoding="utf-8",
    )
    print(f"Generated gRPC modules in {OUT_DIR}")


if __name__ == "__main__":
    main()
