#!/usr/bin/env python
"""Merge LoRA adapter savior_v2/sft_final ke base Llama-Primus-Base (fp16, CPU)."""
import os
import pathlib
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent                       # savior_v2/
BASE = ROOT / "base"
ADAPTER = ROOT / "sft_final"
OUT = ROOT / "merged"
OUT.mkdir(exist_ok=True)

print(f"[1/5] Load base fp16 (CPU): {BASE}")
model = AutoModelForCausalLM.from_pretrained(
    BASE, dtype=torch.float16, low_cpu_mem_usage=True, device_map="cpu"
)

print(f"[2/5] Attach LoRA adapter: {ADAPTER}")
model = PeftModel.from_pretrained(model, ADAPTER)

print("[3/5] merge_and_unload()")
model = model.merge_and_unload()

print(f"[4/5] Save merged model -> {OUT}")
model.save_pretrained(OUT, safe_serialization=True, max_shard_size="5GB")

print("[5/5] Save tokenizer + chat template")
tok = AutoTokenizer.from_pretrained(BASE)
# pakai chat template hasil fine-tune (savior_v2)
ct = (ADAPTER / "chat_template.jinja")
if ct.exists():
    tok.chat_template = ct.read_text(encoding="utf-8")
tok.save_pretrained(OUT)

print("DONE merged ->", OUT)
