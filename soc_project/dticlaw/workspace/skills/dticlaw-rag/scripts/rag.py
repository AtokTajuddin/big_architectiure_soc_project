#!/usr/bin/env python3
"""
DTIClaw RAG — lightweight local retrieval.

Embeddings: Ollama `bge-m3` (1024-dim) via the local Ollama HTTP API.
Store: a single numpy vectors file + JSONL metadata under the store dir.
No ChromaDB / sentence-transformers / torch — keeps RAM low on 8GB.

Commands:
  python3 rag.py ingest <path|dir...> [--store DIR] [--chunk 800] [--overlap 120] [--reset]
  python3 rag.py search "query"       [--store DIR] [--k 5]
  python3 rag.py status               [--store DIR]

Folder-aware: `ingest knowledge/ --reset` rebuild bersih dari SEMUA dokumen di
folder (rekursif). Tambah pengetahuan = taруh file ke knowledge/ lalu re-ingest.
Supported docs: .txt .md .csv .json .html .htm .pdf .docx
"""
import argparse
import json
import os
import re
import sys
import urllib.request

import numpy as np

EMBED_MODEL = os.environ.get("DTICLAW_EMBED_MODEL", "bge-m3")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
DEFAULT_STORE = os.path.join(os.environ.get("DTICLAW_RAG_STORE", "workspace/rag_store"))


def ollama_embed(text):
    # Terima OLLAMA_HOST dgn/atau tanpa skema (mis. "http://127.0.0.1:11434"
    # atau "127.0.0.1:11434") -> hindari URL ganda "http://http://...".
    host = re.sub(r"^https?://", "", OLLAMA_HOST)
    url = f"http://{host}/api/embeddings"
    body = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return np.array(json.load(resp)["embedding"], dtype=np.float32)


def read_doc(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md", ".csv", ".json"):
        return open(path, encoding="utf-8", errors="ignore").read()
    if ext in (".html", ".htm"):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(open(path, encoding="utf-8", errors="ignore").read(), "html.parser")
        for t in soup(["script", "style"]):
            t.decompose()
        return " ".join(soup.get_text(" ").split())
    if ext == ".pdf":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
    if ext == ".docx":
        from docx import Document
        return "\n".join(p.text for p in Document(path).paragraphs)
    raise ValueError(f"unsupported file type: {ext}")


def chunk(text, size, overlap):
    # Line-aware: data list/tabular (jadwal, daftar dosen) tiap baris-entri jadi
    # chunk tersendiri -> retrieval bisa menunjuk baris persis (mis. "Awan A" vs
    # "Awan C"). Baris prosa di-pack sampai `size` tanpa melintasi batas baris.
    # Char-flatten lama menghancurkan struktur baris -> entri jadwal teracak.
    out, buf = [], ""

    def flush():
        nonlocal buf
        if buf.strip():
            out.append(buf.strip())
        buf = ""

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        is_entry = line[:2] in ("- ", "* ", "• ") or bool(re.match(r"^\d+[.)]\s", line))
        if is_entry:
            flush()
            out.append(re.sub(r"^[-*•]\s+|^\d+[.)]\s+", "", line))
        elif len(buf) + len(line) + 1 > size and buf.strip():
            flush()
            buf = line + " "
        else:
            buf += line + " "
    flush()
    return [c for c in out if c.strip()]


def store_paths(store):
    return os.path.join(store, "vectors.npy"), os.path.join(store, "meta.jsonl")


def load_store(store):
    vpath, mpath = store_paths(store)
    if not (os.path.exists(vpath) and os.path.exists(mpath)):
        return None, []
    vecs = np.load(vpath)
    meta = [json.loads(l) for l in open(mpath, encoding="utf-8")]
    return vecs, meta


SUPPORTED = (".txt", ".md", ".csv", ".json", ".html", ".htm", ".pdf", ".docx")


def expand_paths(paths):
    # Folder -> semua dokumen didukung di dalamnya (rekursif). Inilah yang membuat
    # "taруh file di knowledge/ lalu re-ingest" cukup dgn: ingest knowledge/ --reset.
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for fn in sorted(files):
                    if fn.lower().endswith(SUPPORTED) and not fn.startswith("."):
                        out.append(os.path.join(root, fn))
        else:
            out.append(p)
    return out


def cmd_ingest(args):
    os.makedirs(args.store, exist_ok=True)
    if args.reset:  # rebuild bersih -> tak ada duplikat saat re-ingest folder
        for pth in store_paths(args.store):
            if os.path.exists(pth):
                os.remove(pth)
    vecs, meta = load_store(args.store)
    new_vecs, added = [], 0
    for path in expand_paths(args.paths):
        if not os.path.exists(path):
            print(f"⚠️  skip (not found): {path}", file=sys.stderr)
            continue
        try:
            text = read_doc(path)
        except Exception as e:
            print(f"⚠️  skip ({e}): {path}", file=sys.stderr)
            continue
        chunks = chunk(text, args.chunk, args.overlap)
        for idx, c in enumerate(chunks):
            new_vecs.append(ollama_embed(c))
            meta.append({"source": os.path.basename(path), "chunk": idx, "text": c})
            added += 1
        print(f"  • {os.path.basename(path)}: {len(chunks)} chunk", file=sys.stderr)
    if added == 0:
        print(json.dumps({"ingested": 0, "total": len(meta)}))
        return
    stacked = np.vstack(new_vecs)
    vecs = stacked if vecs is None else np.vstack([vecs, stacked])
    vpath, mpath = store_paths(args.store)
    np.save(vpath, vecs)
    with open(mpath, "w", encoding="utf-8") as f:
        for m in meta:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    print(json.dumps({"ingested": added, "total": len(meta), "store": args.store}))


def cmd_search(args):
    vecs, meta = load_store(args.store)
    if vecs is None:
        print(json.dumps({"error": "store kosong; jalankan ingest dulu.", "store": args.store}))
        return
    q = ollama_embed(args.query)
    sims = vecs @ q / (np.linalg.norm(vecs, axis=1) * np.linalg.norm(q) + 1e-8)
    top = np.argsort(-sims)[: args.k]
    hits = [
        {"score": round(float(sims[i]), 4), "source": meta[i]["source"], "chunk": meta[i]["chunk"], "text": meta[i]["text"]}
        for i in top
    ]
    print(json.dumps({"query": args.query, "hits": hits}, ensure_ascii=False, indent=2))


def cmd_status(args):
    vecs, meta = load_store(args.store)
    sources = sorted({m["source"] for m in meta})
    print(json.dumps({
        "store": args.store,
        "vectors": 0 if vecs is None else int(vecs.shape[0]),
        "dim": 0 if vecs is None else int(vecs.shape[1]),
        "documents": len(sources),
        "sources": sources,
        "embed_model": EMBED_MODEL,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="DTIClaw lightweight RAG")
    ap.add_argument("--store", default=DEFAULT_STORE)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_i = sub.add_parser("ingest"); p_i.add_argument("paths", nargs="+"); p_i.add_argument("--chunk", type=int, default=800); p_i.add_argument("--overlap", type=int, default=120); p_i.add_argument("--reset", action="store_true", help="kosongkan store dulu (rebuild bersih)")
    p_s = sub.add_parser("search"); p_s.add_argument("query"); p_s.add_argument("--k", type=int, default=5)
    sub.add_parser("status")
    args = ap.parse_args()
    {"ingest": cmd_ingest, "search": cmd_search, "status": cmd_status}[args.cmd](args)
