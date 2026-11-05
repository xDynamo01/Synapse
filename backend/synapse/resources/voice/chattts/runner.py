"""Offline ChatTTS bridge. The package and model are supplied by the user."""
import argparse
import sys
import wave


def main() -> None:
    import ChatTTS
    import numpy as np
    import torch

    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--language", choices=("en", "zh"), default="en")
    parser.add_argument("--output_file", required=True)
    args = parser.parse_args()
    text = sys.stdin.buffer.read(80001).decode("utf-8").strip()
    if not text or len(text) > 20000:
        raise ValueError("Invalid speech input length")
    device = args.device if args.device != "cuda" or torch.cuda.is_available() else "cpu"
    chat = ChatTTS.Chat()
    if not chat.load(source="custom", custom_path=args.model_path, compile=False, device=torch.device(device)):
        raise RuntimeError("ChatTTS model assets could not be loaded")
    speaker = chat.sample_random_speaker()
    params = ChatTTS.Chat.InferCodeParams(spk_emb=speaker, show_tqdm=False)
    wavs = chat.infer(text, params_infer_code=params, split_text=True, lang=args.language)
    if not wavs or not np.asarray(wavs[0]).size:
        raise RuntimeError("ChatTTS returned empty audio")
    samples = np.asarray(wavs[0], dtype=np.float32).reshape(-1)
    if not np.isfinite(samples).all():
        raise RuntimeError("ChatTTS returned invalid audio")
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(args.output_file, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(pcm.tobytes())


if __name__ == "__main__":
    main()
