"""Provision the pinned local voice packs. No runtime downloads are allowed."""
import argparse
import hashlib
from pathlib import Path
import tempfile
from time import sleep
from urllib.request import urlopen

PACKS = {
    "whisper-base": (
        "Systran/faster-whisper-base", "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66", {
            "config.json": (2309, "867cf1a0fece1394e01d55e287ba2f09a577c046"),
            "model.bin": (145217532, "d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9"),
            "tokenizer.json": (2203239, "7818adb6de9fa3064d3ff81226fdd675be1f6344"),
            "vocabulary.txt": (459861, "c9074644d9d1205686f16d411564729461324b75"),
        },
    ),
    "supertonic-3": (
        "Supertone/supertonic-3", "3cadd1ee6394adea1bd021217a0e650ede09a323", {
            "LICENSE": (15007, "1e2cbe6cef94c8cdf3ed1fcebc0f5317ca7ad5a1"),
            "config.json": (174, "19c2e8b0aa701c1017ca22a22cd519354854e4b1"),
            "onnx/duration_predictor.onnx": (3700147, "c3eb91414d5ff8a7a239b7fe9e34e7e2bf8a8140d8375ffb14718b1c639325db"),
            "onnx/text_encoder.onnx": (36416150, "c7befd5ea8c3119769e8a6c1486c4edc6a3bc8365c67621c881bbb774b9902ff"),
            "onnx/tts.json": (8253, "28575b0793c92607a0f0a292550df9bd17709a79"),
            "onnx/unicode_indexer.json": (277676, "3aaf4d33024aff0be455633c24b3636b3a810150"),
            "onnx/vector_estimator.onnx": (256534781, "883ac868ea0275ef0e991524dc64f16b3c0376efd7c320af6b53f5b780d7c61c"),
            "onnx/vocoder.onnx": (101424195, "085de76dd8e8d5836d6ca66826601f615939218f90e519f70ee8a36ed2a4c4ba"),
            "voice_styles/F1.json": (292046, "421365f307ed1535d8da16845031d0e9fa3e60c5"),
        },
    ),
}


def digest_for(size, expected):
    if len(expected) == 64:
        return hashlib.sha256()
    # Small files are ordinary Git blobs and the pinned source uses Git SHA-1 IDs.
    return hashlib.sha1(f"blob {size}\0".encode("ascii"), usedforsecurity=False)


def matches(path, size, expected):
    if not path.is_file() or path.stat().st_size != size:
        return False
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, lambda: digest_for(size, expected))
    return digest.hexdigest() == expected


def download(url, destination, size, expected):
    if matches(destination, size, expected):
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        temporary = None
        try:
            with urlopen(url, timeout=60) as source, tempfile.NamedTemporaryFile(
                dir=destination.parent, prefix=f".{destination.name}.", delete=False
            ) as target:
                temporary = Path(target.name)
                remaining = size
                digest = digest_for(size, expected)
                while chunk := source.read(min(remaining + 1, 1024 * 1024)):
                    remaining -= len(chunk)
                    if remaining < 0:
                        raise ValueError("Model asset exceeded its pinned size")
                    digest.update(chunk)
                    target.write(chunk)
                if remaining or digest.hexdigest() != expected:
                    raise ValueError("Model asset failed its pinned integrity check")
            temporary.replace(destination)
            return
        except OSError:
            if attempt == 2:
                raise
            sleep(2 ** attempt)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    for directory, (model, revision, files) in PACKS.items():
        for name, (size, digest) in files.items():
            path = args.destination / directory / name
            if args.verify_only:
                if not matches(path, size, digest):
                    parser.exit(1, f"Invalid or missing asset: {directory}/{name}\n")
            else:
                download(f"https://huggingface.co/{model}/resolve/{revision}/{name}?download=true", path, size, digest)
            print(f"Verified {directory}/{name}", flush=True)


if __name__ == "__main__":
    main()
