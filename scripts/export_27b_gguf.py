"""Export the trained Qwen3.6-27B LoRA to GGUF q4_k_m (AI-041).

Loads the base model with the trained adapter, then exports a standalone
GGUF for llama.cpp inference on :8080. Memory-conscious: exports from the
loaded 4-bit model (unsloth chunks the dequant/quantize) rather than
materializing the full 16-bit merge.

Run:
    UNSLOTH_MOE_BACKEND=native_torch \
      ~/.unsloth/studio/unsloth_studio/Scripts/python.exe scripts/export_27b_gguf.py
"""

from __future__ import annotations

import shutil  # noqa: E402
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from unsloth import FastLanguageModel  # noqa: E402

BASE_MODEL = "unsloth/Qwen3.6-27B"
ADAPTER = PROJECT_ROOT / "training_data" / "lora_checkpoints" / "qwen36-27b-playwright-skeleton"
OUTPUT = Path.home() / ".lmstudio" / "models" / "unsloth" / "qwen36-27b-playwright-skeleton"
MERGED = PROJECT_ROOT / "training_data" / "merged_qwen36_27b"  # scratch — converted+quantized below, then removed
HF_CACHE = Path.home() / ".cache" / "huggingface" / "hub" / "models--unsloth--Qwen3.6-27B" / "snapshots"


def _copy_base_config_to(target: Path) -> None:
    """The GGUF converter needs config.json + tokenizer files in the target dir."""
    snapshot = next(HF_CACHE.iterdir(), None)
    if snapshot is None:
        raise RuntimeError(f"no snapshot in {HF_CACHE}")
    target.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt"):
        src = snapshot / name
        if src.exists():
            shutil.copy2(src, target / name)
    print(f"Copied base config files from {snapshot.name}")


def main() -> None:
    print(f"Loading base {BASE_MODEL}...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=1024,
        load_in_4bit=True,
    )
    print("Loading trained adapter...")
    model.load_adapter(str(ADAPTER))  # mutates in place, returns None

    print("Merging LoRA into base (16-bit) -> scratch dir...")
    model.save_pretrained_merged(str(MERGED), tokenizer, save_method="merged_16bit")
    print("Merged model written.")

    _copy_base_config_to(MERGED)

    print(f"Exporting GGUF q4_k_m -> {OUTPUT} (this takes a while for 27B)...")
    model.save_pretrained_gguf(str(MERGED), tokenizer, quantization_method="q4_k_m")

    # Move the GGUF into the final models dir.
    OUTPUT.mkdir(parents=True, exist_ok=True)
    import shutil as _sh

    for f in MERGED.glob("*.gguf"):
        _sh.copy2(f, OUTPUT / f.name)
        print(f"Copied {f.name} -> {OUTPUT}")
    print(f"Done — GGUF saved to {OUTPUT}")


if __name__ == "__main__":
    main()
