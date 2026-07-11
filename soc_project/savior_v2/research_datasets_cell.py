# ============================================================================
# RESEARCH DATASETS — anti-halusinasi (grounding/refusal) + tool-use
# Sisipkan SETELAH cell augmentasi (yang punya all_rows, add_convo, system_prompt).
# Sumber (riset): SQuAD v2 (abstain saat tak ada jawaban di konteks) & Glaive
# Function-Calling v2 (loop user->call->FUNCTION RESPONSE->sintesis).
# Robust: per-dataset try/except, cap N, resume_download. Cek jumlah baris yg tertambah.
# ============================================================================
import os, re, json, random
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")  # download lebih tahan putus
random.seed(11)

try:
    all_rows; add_convo; system_prompt  # noqa
except NameError:
    all_rows = []
    system_prompt = "You are Savior v2, a bilingual SOC copilot. Answer only from provided evidence; never invent."
    def add_convo(turns):
        msgs = [{"role": "system", "content": system_prompt}]
        for r, c in turns:
            if r in ("user", "assistant") and str(c).strip():
                msgs.append({"role": r, "content": str(c).strip()})
        if len(msgs) >= 3 and msgs[-1]["role"] == "assistant":
            all_rows.append({"messages": msgs})

# Knob jumlah (seimbangkan vs base; jangan terlalu besar agar gaya SOC tetap dominan)
N_SQUAD_REFUSE   = 1200   # unanswerable -> "tidak ada di konteks, tidak menebak"
N_SQUAD_GROUND   = 1200   # answerable   -> jawab HANYA dari konteks
N_GLAIVE_TOOL    = 1500   # tool-use loop

def _load(name, **kw):
    from datasets import load_dataset
    return load_dataset(name, **kw)

# ---------------------------------------------------------------------------
# 1) SQuAD v2 -> anti-halusinasi (grounding + abstain). Dibingkai gaya "evidence".
# ---------------------------------------------------------------------------
_REFUSE_TPL = [
    "Jawabannya TIDAK ada di konteks yang diberikan, jadi saya tidak menebak. "
    "Beri konteks/evidence yang relevan dulu.",
    "The provided context does not contain this; I won't guess. "
    "Please supply the relevant evidence.",
]
try:
    sq = _load("rajpurkar/squad_v2", split="train")
    idx = list(range(len(sq))); random.shuffle(idx)
    nr = ng = 0; b = len(all_rows)
    for i in idx:
        if nr >= N_SQUAD_REFUSE and ng >= N_SQUAD_GROUND:
            break
        r = sq[i]; ctx = r["context"].strip(); q = r["question"].strip()
        ans = r["answers"]["text"]
        user = (f"Context (evidence):\n{ctx}\n\nQuestion: {q}\n"
                "Answer ONLY from the context. If it's not in the context, say so and don't guess.")
        if not ans:  # unanswerable
            if nr < N_SQUAD_REFUSE:
                add_convo([("user", user), ("assistant", random.choice(_REFUSE_TPL))]); nr += 1
        else:
            if ng < N_SQUAD_GROUND:
                add_convo([("user", user), ("assistant", str(ans[0]).strip())]); ng += 1
    print(f"  + SQuAD v2: refuse={nr}, grounded={ng} (total {len(all_rows)-b})")
except Exception as e:
    print(f"  SQuAD v2 SKIP: {repr(e)[:140]}")

# ---------------------------------------------------------------------------
# 2) Glaive Function-Calling v2 -> tool-use loop (call -> FUNCTION RESPONSE -> sintesis)
# ---------------------------------------------------------------------------
def parse_glaive(system, chat):
    """Ubah 'chat' Glaive jadi list (role, content) loop tool yg template-safe."""
    chat = chat.replace("<|endoftext|>", "")
    # pecah per penanda turn, pertahankan penanda
    parts = re.split(r"(USER:|ASSISTANT:|FUNCTION RESPONSE:)", chat)
    turns, role = [], None
    for p in parts:
        p = p.strip()
        if p in ("USER:", "ASSISTANT:", "FUNCTION RESPONSE:"):
            role = p; continue
        if not p or role is None:
            continue
        if role == "USER:":
            turns.append(("user", p))
        elif role == "FUNCTION RESPONSE:":
            turns.append(("user", f"[FUNCTION RESPONSE]\n{p}"))   # hasil tool sbg user turn (template-safe)
        else:  # ASSISTANT
            fc = re.search(r"<functioncall>\s*(\{.*\})", p, re.DOTALL)
            if fc:
                turns.append(("assistant", f"TOOL_CALL: {fc.group(1).strip()}"))
            text = re.sub(r"<functioncall>\s*\{.*\}\s*", "", p, flags=re.DOTALL).strip()
            if text:
                turns.append(("assistant", text))
    # tempel daftar fungsi ke user pertama agar model tahu tool tersedia
    if turns and turns[0][0] == "user" and system:
        fns = system.replace("You are a helpful assistant with access to the following functions. Use them if required -", "").strip()
        turns[0] = ("user", f"[AVAILABLE TOOLS]\n{fns}\n\n{turns[0][1]}")
    return turns

try:
    gl = _load("glaiveai/glaive-function-calling-v2", split="train")
    idx = list(range(len(gl))); random.shuffle(idx)
    n = 0; b = len(all_rows)
    for i in idx:
        if n >= N_GLAIVE_TOOL: break
        try:
            turns = parse_glaive(gl[i].get("system", ""), gl[i]["chat"])
        except Exception:
            continue
        # hanya ambil yang benar2 ada loop tool (call + response) -> ajarkan sintesis
        if any("TOOL_CALL:" in t[1] for t in turns) and any("[FUNCTION RESPONSE]" in t[1] for t in turns):
            before = len(all_rows); add_convo(turns)
            if len(all_rows) > before: n += 1
    print(f"  + Glaive tool-use: {n} (total {len(all_rows)-b})")
except Exception as e:
    print(f"  Glaive SKIP: {repr(e)[:140]}")

print(f"TOTAL all_rows setelah research datasets: {len(all_rows)}")
# Catatan: dataset lain yg relevan kalau mau diperkaya:
#   declare-lab/Trust-Data (refuse-in-RAG, utk DPO), flowaicom/RAGTruth_test (grounding label),
#   Salesforce/xlam-function-calling-60k & NousResearch/hermes-function-calling-v1 (tool-use).
