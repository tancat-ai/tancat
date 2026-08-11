"""Train Qwen3.6-27B QLoRA on the Playwright skeleton corpus (AI-041).

Direct Unsloth training path that bypasses Unsloth Studio's 16-bit flip for
"brand-new" architectures (Studio disables 4-bit QLoRA for Qwen3.6 → 16-bit
27B can't fit the 64 GB unified pool → fused-CE crash). The direct path
loads 4-bit (19.3 GB) and trains completion-only with the fused CE fine.

Run (requires the Studio venv — it has the gfx1151 ROCm build):
    UNSLOTH_MOE_BACKEND=native_torch \\
    .venv-studio/Scripts/python.exe scripts/train_27b_qlora.py

Hyperparameters follow the runbook (docs/sessions/2026-08-09_unsloth_training_runbook.md §4):
context 2048, lr 2e-4, LoRA 16/32/0.05 all modules, 3 epochs,
batch 4 / grad-accum 8, AdamW 8-bit, linear warmup 5, completion-only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from datasets import Dataset  # noqa: E402
from unsloth import FastLanguageModel, UnslothTrainer, UnslothTrainingArguments  # noqa: E402
from unsloth_zoo.dataset_utils import train_on_responses_only  # noqa: E402

MODEL = "unsloth/Qwen3.6-27B"
CORPUS = PROJECT_ROOT / "training_data" / "playwright_skeleton_alpaca.jsonl"
OUTPUT_DIR = PROJECT_ROOT / "training_data" / "lora_checkpoints" / "qwen36-27b-playwright-skeleton"

MAX_SEQ_LEN = 1024  # 2048 thrashes this box (44GB model+activations near 64GB physical); skeletons are <500 tok
LR = 2e-4
R, ALPHA, DROPOUT = 16, 32, 0.05
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
EPOCHS = 3
BATCH = 4  # 4x8=32 effective, 15 steps, worked for step 1
GRAD_ACCUM = 8  # 4x8=32 effective batch
WARMUP_STEPS = 5


def load_corpus() -> Dataset:
    rows = [json.loads(line) for line in CORPUS.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"Corpus: {len(rows)} rows from {CORPUS.name}")
    data = [{"text": f"### Instruction:\n{r['instruction']}\n\n### Response:\n{r['output']}"} for r in rows]
    return Dataset.from_list(data)


def main() -> None:
    print(f"Loading {MODEL} in 4-bit QLoRA...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        MODEL,
        max_seq_length=MAX_SEQ_LEN,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=R,
        lora_alpha=ALPHA,
        lora_dropout=DROPOUT,
        target_modules=TARGET_MODULES,
        use_gradient_checkpointing="unsloth",
    )

    dataset = load_corpus()
    trainer = UnslothTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        args=UnslothTrainingArguments(
            per_device_train_batch_size=BATCH,
            gradient_accumulation_steps=GRAD_ACCUM,
            num_train_epochs=EPOCHS,
            learning_rate=LR,
            warmup_steps=WARMUP_STEPS,
            logging_steps=1,
            optim="adamw_8bit",
            lr_scheduler_type="linear",
            output_dir=str(OUTPUT_DIR),
            save_strategy="epoch",
            report_to="none",
        ),
    )
    trainer = train_on_responses_only(
        trainer,
        instruction_part="### Instruction:",
        response_part="### Response:",
    )

    print(f"\nTraining: {len(dataset)} rows | {EPOCHS} epochs | batch {BATCH}x{GRAD_ACCUM}={BATCH * GRAD_ACCUM}")
    trainer.train()
    trainer.save_model(str(OUTPUT_DIR))
    print(f"\nDone — LoRA checkpoint saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
