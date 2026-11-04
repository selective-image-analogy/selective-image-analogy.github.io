# Record of how the all-edits-on Qwen renders (all_is_correct_qwen/*/no_supp.png) were made. Needs the SIA code
# base (training/, visual_analogy/), the Qwen-Image-2.1 weights and the ExLoRA checkpoint-5000; run from the code dir:
#   python qwen_full_render.py <exlora>/checkpoint-5000 <out_dir> cases.json   (cases.json: list of benchmark case ids)
"""Render the all-edits-kept output (nothing suppressed) for chosen benchmark cases,
same checkpoint / settings as s2_5000_reorder (seed 0, 40 steps, ExLoRA with no mask)."""
import os, sys, json, time
from pathlib import Path
sys.path.insert(0, os.getcwd())
os.environ.setdefault("WANDB_MODE", "disabled"); os.environ.setdefault("HF_HOME", "/workspace/.hf_home")
from omegaconf import OmegaConf
from training.train_exlora_qwen21 import (ANALORA_TARGET_MODULES, EXLORA_TARGET_MODULES, build_analogy_prompt,
    encode_prompt, generate_qwen21, harmonize_images_qwen21, load_pipeline_qwen21, prepare_conditions)
import torch
from training.eval_benchmark_qwen21 import load_split
from visual_analogy.utils import load_analora_state_dict
from visual_analogy.utils.selective_lora import inject_analora_modules, inject_exlora_modules

ckpt, out, cases_file = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
want = json.load(open(cases_file))
cfg = OmegaConf.load("training/configs/train_exlora_qwen21.yaml")
device = torch.device("cuda"); rank = cfg.lora_rank
pipe = load_pipeline_qwen21(cfg.pretrained_model_name_or_path); tr = pipe.transformer
inject_analora_modules(tr, ANALORA_TARGET_MODULES, r=rank, alpha=rank, dropout=0.0)
load_analora_state_dict(tr, os.path.join(ckpt, "base_lora.pt"), "cpu")
inject_exlora_modules(tr, EXLORA_TARGET_MODULES, r=rank, alpha=rank, dropout=0.0)
state = torch.load(os.path.join(ckpt, "selective_lora.pt"), map_location="cpu", weights_only=True)
_, unexpected = tr.load_state_dict(state, strict=False); assert not unexpected
pipe.to(device); tr.eval()
cases = {c["id"]: c for c in load_split("analogy_benchmark")}
t0 = time.time()
for cid in want:
    p = out / (cid.replace("/", "__") + ".png")
    if p.exists(): continue
    c = cases[cid]
    a, ap, b = harmonize_images_qwen21(c["a"], c["a_prime"], c["b"], c["b"])[:3]
    cond = prepare_conditions(pipe, [a, ap, b], cfg.get("resolution", 512), device)
    emb, pad = encode_prompt(pipe, build_analogy_prompt(c["edits"], c["edits"]), cond, device)
    gen = torch.Generator(device=device).manual_seed(0)
    img = generate_qwen21(pipe, cond, emb, pad, cfg.get("num_val_inference_steps", 40), generator=gen,
                          exlora_text_mask=None, use_kv_cache=cfg.get("use_kv_cache", True),
                          guide_text_mask=None, guidance_scale=1.0)
    p.parent.mkdir(parents=True, exist_ok=True); img.save(p)
    print(cid, f"{time.time()-t0:.0f}s", flush=True)
print("DONE", flush=True)
