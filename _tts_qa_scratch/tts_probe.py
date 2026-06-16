#!/usr/bin/env python3
"""
Studio-side TTS probe. Loads Qwen3-TTS once and renders short clips for a list
of {id, text} items, using the SAME params as the production podcast pipeline
(model, voice ref, ref_text, temperature). Writes one wav per (id, take).

Non-destructive: reads the production voice reference, writes only to its own
scratch dir. Does not touch the pipeline, scripts, or any published audio.

Usage:  python3 tts_probe.py <items.json> <out_dir> [--voice health_longevity] [--takes 2]
items.json: [{"id": "old", "text": "..."}, {"id": "newA", "text": "..."}]
"""
import sys, os, json, time, argparse

KS = os.path.expanduser("~/knowledge-studio")
VOICE_DIR = os.path.join(KS, "podcast_audio", "voice_roster")
MODEL_PATH = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"
REF_TEXT = ("Hey, welcome back. Today we are looking at what might actually be "
            "the most important shift in AI in the past six months, and it is "
            "not what you would expect from reading the headlines.")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("items"); ap.add_argument("out_dir")
    ap.add_argument("--voice", default="health_longevity")
    ap.add_argument("--takes", type=int, default=2)
    ap.add_argument("--temperature", type=float, default=0.7)
    a = ap.parse_args()

    os.makedirs(a.out_dir, exist_ok=True)
    voice_ref = os.path.join(VOICE_DIR, f"{a.voice}_voice.wav")
    if not os.path.exists(voice_ref):
        print(f"!! voice ref missing: {voice_ref}"); sys.exit(1)

    items = json.load(open(a.items))
    from mlx_audio.tts.generate import generate_audio
    from mlx_audio.tts.utils import load_model
    import mlx.core as mx

    print(f"loading model {MODEL_PATH} ...", flush=True)
    model = load_model(model_path=MODEL_PATH)
    print(f"model loaded (sr={model.sample_rate})", flush=True)

    manifest = []
    for it in items:
        for t in range(a.takes):
            prefix = os.path.join(a.out_dir, f"{it['id']}_take{t}")
            start = time.time()
            generate_audio(
                text=it["text"], model=model, ref_audio=voice_ref,
                ref_text=REF_TEXT, lang_code="en", file_prefix=prefix,
                audio_format="wav", join_audio=True, verbose=False,
                temperature=a.temperature, max_tokens=4096,
            )
            wav = f"{prefix}.wav"
            ok = os.path.exists(wav)
            print(f"  {it['id']} take{t}: {'OK' if ok else 'FAIL'} "
                  f"({time.time()-start:.0f}s)", flush=True)
            manifest.append({"id": it["id"], "take": t, "text": it["text"],
                             "wav": os.path.basename(wav) if ok else None})
            mx.clear_cache()
    json.dump(manifest, open(os.path.join(a.out_dir, "manifest.json"), "w"), indent=2)
    print("PROBE DONE")

if __name__ == "__main__":
    main()
