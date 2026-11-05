"""One offline CPU synthesis process; dependencies live outside the sidecar."""
import argparse
import sys
import wave


def main() -> None:
    import numpy as np
    import onnxruntime as ort
    from kokoro_onnx import Kokoro

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--voices", required=True)
    parser.add_argument("--voice", required=True)
    parser.add_argument("--lang", required=True)
    parser.add_argument("--output_file", required=True)
    args = parser.parse_args()
    text = sys.stdin.buffer.read(80001).decode("utf-8").strip()
    if not text or len(text) > 20000:
        raise ValueError("Invalid speech input length")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(args.model, options, providers=["CPUExecutionProvider"])
    engine = Kokoro.from_session(session, args.voices)
    samples, rate = engine.create(text, voice=args.voice, lang=args.lang, speed=1.0)
    if not samples.size or not np.isfinite(samples).all():
        raise ValueError("Invalid synthesis output")
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(args.output_file, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(pcm.tobytes())


if __name__ == "__main__":
    main()
