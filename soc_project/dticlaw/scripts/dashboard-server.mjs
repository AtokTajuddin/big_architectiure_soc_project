#!/usr/bin/env node
// DTIClaw Dashboard — serves the standalone Control UI and runs agent turns.
//
// Retrieval is DETERMINISTIC (RAG hook): for academic questions this server
// runs rag.py itself, injects the retrieved context + sources into the prompt,
// and the local model only has to synthesize. A 7B local model is unreliable at
// agentic tool-calling (it leaks the command as text or picks the wrong row), so
// guaranteeing retrieval here keeps answers grounded and fast. Non-academic
// questions go straight to the agent (which can still use research/writer skills).
import { createServer } from "node:http";
import { readFileSync, existsSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { join, extname, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import { DatabaseSync } from "node:sqlite";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DTICLAW_DIR = join(__dirname, "..");
const OPENCLAW = join(DTICLAW_DIR, "openclaw.mjs");
const UI_DIR = join(DTICLAW_DIR, "web");
const DTICLAW_PY = process.env.DTICLAW_PY || join(DTICLAW_DIR, ".venv/bin/python");
const RAG_SCRIPT = join(DTICLAW_DIR, "workspace/skills/dticlaw-rag/scripts/rag.py");
const RAG_STORE = join(DTICLAW_DIR, "workspace/rag_store");
const WRITER_DIR = join(DTICLAW_DIR, "workspace/skills/dticlaw-writer/scripts");
const OUTPUT_DIR = join(DTICLAW_DIR, "output");

// Histori percakapan: SQLite per-sesi -> user bisa buka chat lama.
mkdirSync(join(DTICLAW_DIR, ".dticlaw-state"), { recursive: true });
const db = new DatabaseSync(join(DTICLAW_DIR, ".dticlaw-state", "chat-history.db"));
db.exec(`CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT NOT NULL, role TEXT NOT NULL,
  content TEXT NOT NULL, sources TEXT, file TEXT, ts INTEGER NOT NULL)`);
const _insMsg = db.prepare("INSERT INTO messages (session,role,content,sources,file,ts) VALUES (?,?,?,?,?,?)");
function saveMsg(session, role, content, sources, file) {
  if (!session || !content) return;
  try { _insMsg.run(String(session), role, String(content), sources ? JSON.stringify(sources) : null, file || null, Date.now()); } catch {}
}

const PORT = parseInt(process.env.DTICLAW_UI_PORT || "3737", 10);
const GATEWAY_PORT = parseInt(process.env.DTICLAW_GATEWAY_PORT || "18789", 10);
const GATEWAY_URL = `http://127.0.0.1:${GATEWAY_PORT}`;
const AGENT_ID = process.env.DTICLAW_AGENT_ID || "dticlaw";
const AGENT_TIMEOUT_MS = parseInt(process.env.DTICLAW_AGENT_TIMEOUT_MS || "600000", 10);
const RAG_TIMEOUT_MS = parseInt(process.env.DTICLAW_RAG_TIMEOUT_MS || "60000", 10);
const RAG_TOP_K = parseInt(process.env.DTICLAW_RAG_K || "6", 10);

// Pertanyaan akademik -> retrieve dari basis pengetahuan lokal (jadwal/dosen/dsb).
const ACADEMIC_RE =
  /jadwal|kelas|ruang|dosen|kurikulum|\bsks\b|kalender|peraturan|mata.?kuliah|matkul|semester|akademik|prodi|departemen|perkuliahan|kuliah|magang|visi|misi/i;
// "list semua" -> butuh recall tinggi (mis. semua entri Kelas A se-pekan).
const BROAD_RE = /keseluruhan|semua|seluruh|daftar|list|apa saja|setiap hari|tiap hari|sepekan|seminggu/i;
// Permintaan buat dokumen -> hook doc-gen deterministik: 7b andal menyusun KONTEN
// (markdown/tabel) tapi tak andal memanggil tool (sering halusinasi "sudah dibuat"
// tanpa eksekusi). Maka server yang menjalankan generator writer atas konten model.
const DOC_RE =
  /\b(buat\w*|bikin\w*|generate|generasikan|susun\w*|ekspor\w*|export\w*|simpan\w*|unduh\w*|download)\b[\s\S]*\b(file|dokumen|laporan|proposal|docx|word|pdf|excel|xlsx|spreadsheet|csv|tabel)\b|\b(dalam|ke|jadi|jadikan|bentuk|format|sebagai)\s+(file\s+|bentuk\s+)?(pdf|docx|word|excel|xlsx|spreadsheet|csv)\b/i;

const MIME = {
  ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".png": "image/png", ".svg": "image/svg+xml",
  ".ico": "image/x-icon", ".woff2": "font/woff2",
  ".pdf": "application/pdf", ".csv": "text/csv",
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
};

function serveStatic(req, res) {
  const rel = req.url === "/" ? "/index.html" : req.url.split("?")[0];
  const fullPath = join(UI_DIR, rel);
  if (!fullPath.startsWith(UI_DIR) || !existsSync(fullPath)) {
    const fallback = join(UI_DIR, "index.html");
    res.writeHead(existsSync(fallback) ? 200 : 404, { "Content-Type": "text/html" });
    res.end(existsSync(fallback) ? readFileSync(fallback) : "Not found");
    return;
  }
  res.writeHead(200, { "Content-Type": MIME[extname(fullPath).toLowerCase()] || "application/octet-stream" });
  res.end(readFileSync(fullPath));
}

// Deterministic retrieval: run rag.py search, return {hits, sources} or null.
function retrieveContext(query, k = RAG_TOP_K) {
  return new Promise((resolve) => {
    const args = [RAG_SCRIPT, "--store", RAG_STORE, "search", query, "--k", String(k)];
    const child = spawn(DTICLAW_PY, args, { cwd: DTICLAW_DIR, env: process.env });
    let out = "";
    const timer = setTimeout(() => { child.kill("SIGKILL"); resolve(null); }, RAG_TIMEOUT_MS);
    child.stdout.on("data", (d) => (out += d));
    child.on("close", () => {
      clearTimeout(timer);
      try {
        const hits = (JSON.parse(out).hits || [])
          .filter((h) => h.text)
          // Buang null byte & control char (artefak ekstraksi PDF) — `spawn` menolak
          // arg ber-null, dan ini mengotori prompt model.
          .map((h) => ({ ...h, text: h.text.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g, " ").replace(/\s+/g, " ").trim() }))
          .filter((h) => h.text);
        resolve(hits.length ? hits : null);
      } catch { resolve(null); }
    });
    child.on("error", () => { clearTimeout(timer); resolve(null); });
  });
}

// Kata tanya/pengisi generik (BUKAN kata-benda domain spt komputasi/awan/dosen).
const STOP = new Set(
  ("jadwal kapan saja semua seluruh keseluruhan daftar list apa sebutkan tolong " +
   "mohon mata kuliah matkul pukul ruang hari untuk yang dan atau pada adalah " +
   "berapa siapa dimana mana setiap tiap sepekan seminggu ada bisa kah kelas " +
   "ini itu dari ke di").split(" ")
);

// Saring hit ke yang berbagi kata-kunci signifikan dgn query (BM25-lite, generik).
// Model kecil (7b) jauh lebih akurat dgn konteks fokus drpd 30 entri campur; ini
// menyaring berdasarkan overlap token, TIDAK menanam jawaban tertentu (no hardcode).
function focusHits(query, hits) {
  const terms = [...new Set(query.toLowerCase().match(/[a-z0-9]+/g) || [])]
    .filter((t) => t.length >= 4 && !STOP.has(t));
  if (terms.length === 0) return hits;
  const need = Math.max(1, Math.ceil(terms.length * 0.5));
  let kept = hits.filter((h) => {
    const lt = h.text.toLowerCase();
    return terms.filter((t) => lt.includes(t)).length >= need;
  });
  if (!kept.length) kept = hits; // jangan over-filter sampai konteks kosong
  // Bila pertanyaan menyebut kelas spesifik ("kelas A"), batasi ke entri kelas itu.
  // Parsing query (generik), bukan menanam jawaban: jadwal ditulis "<matkul> A (n SKS)".
  // Konteks kecil & seragam -> model 7b tak lagi melewatkan entri saat enumerasi.
  const cm = query.match(/\bkelas\s+([a-z](?:\s*(?:dan|,|&|\/|\s)\s*[a-z])*)/i);
  if (cm) {
    const letters = [...cm[1].matchAll(/\b([a-z])\b/gi)].map((m) => m[1].toUpperCase());
    if (letters.length) {
      const re = new RegExp(`\\b(${letters.join("|")})\\s*\\(`);
      const byClass = kept.filter((h) => re.test(h.text));
      if (byClass.length) kept = byClass;
    }
  }
  return kept;
}

function buildGroundedPrompt(question, hits) {
  const ctx = hits
    .map((h, i) => `[${i + 1}] (sumber: ${h.source}) ${h.text}`)
    .join("\n");
  return (
    `KONTEKS berisi ${hits.length} entri bernomor [1]..[${hits.length}]. ` +
    "Tulis baris \"JAWABAN:\" lalu daftar berpoin SEMUA entri di KONTEKS yang " +
    "menjawab PERTANYAAN — salin lengkap hari, jam, ruang, SKS, dosen, dan sumber " +
    "tiap entri (masukkan juga yang berkolom \"?\"). Sertakan SETIAP entri yang " +
    "cocok, jangan melewatkan satu pun walau mata kuliah/kelas sama muncul beberapa " +
    "kali. Jika tidak ada satu pun yang cocok, tulis \"JAWABAN: Informasi tidak " +
    "ditemukan dalam basis pengetahuan.\" Jawab HANYA dari KONTEKS, jangan mengarang, " +
    "jangan panggil tool.\n\n" +
    `KONTEKS:\n${ctx}\n\nPERTANYAAN: ${question}`
  );
}

function docFormat(q) {
  if (/\b(xlsx|excel|spreadsheet)\b/i.test(q)) return "xlsx";
  if (/\bcsv\b/i.test(q)) return "csv";
  if (/\bpdf\b/i.test(q)) return "pdf";
  return "docx"; // default: dokumen teks
}

// Ambil tabel Markdown pertama dari teks model -> array baris (utk xlsx/csv).
function parseMdTable(md) {
  const lines = md.split("\n").map((l) => l.trim()).filter((l) => l.startsWith("|"));
  const rows = lines
    .filter((l) => !/^\|?[\s:|-]+\|?$/.test(l)) // buang baris pemisah |---|---|
    .map((l) => l.replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
  return rows.length ? rows : null;
}

function runWriter(args) {
  return new Promise((resolve) => {
    const child = spawn(DTICLAW_PY, args, { cwd: DTICLAW_DIR, env: process.env });
    let out = "", err = "";
    const timer = setTimeout(() => { child.kill("SIGKILL"); resolve({ code: -1, err: "writer timeout" }); }, 60000);
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("close", (code) => { clearTimeout(timer); resolve({ code, out, err }); });
    child.on("error", (e) => { clearTimeout(timer); resolve({ code: -1, err: e.message }); });
  });
}

// Filler/format/verb words: dibuang saat mengukur apakah permintaan punya "topik".
const DOC_FILLER = new Set(
  ("buat buatkan buatlah bikin bikinkan generate generasikan susun susunkan ekspor export " +
   "simpan unduh download dalam bentuk jadi jadikan format sebagai file dokumen laporan " +
   "proposal pdf docx word excel xlsx spreadsheet csv tabel tolong mohon ini itu saja dong " +
   "sih kan nya juga dari atas tadi").split(" ")
);

// Hook doc-gen: model hasilkan konten (markdown/tabel), server render ke file.
// Follow-up tanpa topik ("jadikan pdf", "buatkan dalam bentuk pdf") -> render jawaban
// bot TERAKHIR di sesi ini (dari DB histori), bukan generate dari konteks kosong.
async function generateDoc(q, getSession, chatSession) {
  const fmt = docFormat(q);
  const wantTable = fmt === "xlsx" || fmt === "csv";
  let sources = null, content = null;

  const topic = (q.toLowerCase().match(/[a-z0-9]+/g) || []).filter((w) => w.length >= 3 && !DOC_FILLER.has(w));
  if (topic.length < 2 && chatSession) {
    const prev = db.prepare(
      "SELECT content, sources FROM messages WHERE session=? AND role='bot' AND content NOT LIKE '✅ Dokumen%' ORDER BY id DESC LIMIT 1").get(chatSession);
    if (prev && prev.content && prev.content.trim().length > 20) {
      content = prev.content.trim();
      sources = prev.sources ? JSON.parse(prev.sources) : null;
    }
  }

  if (!content) {  // ada topik -> generate baru dari knowledge base
    let ctxBlock = "";
    if (ACADEMIC_RE.test(q)) {
      const hits = await retrieveContext(q, BROAD_RE.test(q) ? 30 : RAG_TOP_K);
      if (hits) {
        const f = focusHits(q, hits);
        ctxBlock = "\n\nGunakan HANYA data berikut (jangan mengarang):\n" +
          f.map((h, i) => `[${i + 1}] ${h.text}`).join("\n");
        sources = [...new Set(f.map((h) => h.source))];
      }
    }
    const genPrompt = wantTable
      ? "Keluarkan HANYA satu tabel Markdown (baris pertama = header) sesuai permintaan. " +
        "Tanpa kalimat pembuka/penutup, tanpa kode, tanpa memanggil tool." + ctxBlock +
        `\n\nPERMINTAAN: ${q}`
      : "Keluarkan HANYA isi dokumen dalam Markdown (judul '# ', sub-bab '## ', poin '- ', " +
        "tabel Markdown bila perlu). Langsung konten, tanpa basa-basi, tanpa blok kode, " +
        "tanpa memanggil tool." + ctxBlock + `\n\nPERMINTAAN: ${q}`;
    const r = await runAgent(genPrompt, getSession());
    if (r.error || !r.reply) return { error: r.error || "Model tak menghasilkan konten." };
    content = r.reply.replace(/^```[a-z]*\n?|```$/gim, "").trim();
  }

  mkdirSync(OUTPUT_DIR, { recursive: true });
  const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const outPath = join(OUTPUT_DIR, `dokumen-${ts}.${fmt}`);
  const title = "Dokumen DTIClaw";
  let res, tmp;
  if (wantTable) {
    const rows = parseMdTable(content);
    if (!rows) return { error: "Model tak menghasilkan tabel yang bisa diparse." };
    tmp = join(OUTPUT_DIR, `.tmp-${ts}.json`);
    writeFileSync(tmp, JSON.stringify({ sheets: [{ name: "Data", rows }] }));
    res = await runWriter([join(WRITER_DIR, "xlsx_writer.py"), "--input", tmp, "--output", outPath, "--title", title]);
  } else {
    tmp = join(OUTPUT_DIR, `.tmp-${ts}.md`);
    writeFileSync(tmp, content);
    const script = fmt === "pdf" ? "pdf_writer.py" : "docx_writer.py";
    res = await runWriter([join(WRITER_DIR, script), "--title", title, "--author", "Atok Tajuddin", "--input", tmp, "--output", outPath]);
  }
  rmSync(tmp, { force: true }); // bersihkan konten sementara
  if (res.code !== 0 || !existsSync(outPath)) {
    return { error: `Gagal render ${fmt}: ${(res.err || res.out || "").split("\n").pop()}` };
  }
  const rel = outPath.slice(DTICLAW_DIR.length + 1);
  return { reply: `✅ Dokumen ${fmt.toUpperCase()} dibuat: ${rel}\n\n--- pratinjau konten ---\n${content.slice(0, 600)}`, file: rel, sources };
}

// Extract the agent's visible reply from `openclaw agent --json` output.
function extractReply(stdout) {
  const start = stdout.indexOf("{");
  if (start === -1) return null;
  let depth = 0, end = -1;
  for (let i = start; i < stdout.length; i++) {
    if (stdout[i] === "{") depth++;
    else if (stdout[i] === "}") { depth--; if (depth === 0) { end = i; break; } }
  }
  if (end === -1) return null;
  try {
    const data = JSON.parse(stdout.slice(start, end + 1));
    const payloads = data?.result?.payloads;
    if (Array.isArray(payloads)) {
      const text = payloads.map((p) => p?.text).filter(Boolean).join("\n").trim();
      if (text) return text;
    }
    return data?.summary || null;
  } catch {
    return null;
  }
}

function runAgent(message, session) {
  return new Promise((resolve) => {
    const args = ["agent", "--agent", AGENT_ID, "--message", message, "--json"];
    if (session) args.push("--session-key", String(session));
    const child = spawn("node", [OPENCLAW, ...args], { cwd: DTICLAW_DIR, env: process.env });
    let stdout = "", stderr = "";
    const timer = setTimeout(() => { child.kill("SIGKILL"); resolve({ error: "Timeout: agent terlalu lama merespons." }); }, AGENT_TIMEOUT_MS);
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("close", () => {
      clearTimeout(timer);
      const reply = extractReply(stdout);
      if (reply) resolve({ reply });
      else resolve({ error: "Agent tidak mengembalikan balasan. " + (stderr.split("\n").filter(Boolean).pop() || "") });
    });
    child.on("error", (e) => { clearTimeout(timer); resolve({ error: e.message }); });
  });
}

const server = createServer((req, res) => {
  const url = req.url || "/";

  if (url === "/chat" && req.method === "POST") {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", async () => {
      try {
        const { message, session } = JSON.parse(body || "{}");
        const q = String(message || "").trim();
        if (!q) {
          res.writeHead(400, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: "Pesan kosong." }));
          return;
        }
        const newSession = () => `auto-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        // Doc-gen diprioritaskan: "buatkan laporan/excel jadwal ..." cocok ke DOC_RE
        // & ACADEMIC_RE; yang diinginkan user adalah FILE, bukan jawaban chat.
        if (DOC_RE.test(q)) {
          const r = await generateDoc(q, newSession, session);
          saveMsg(session, "user", q);
          saveMsg(session, "bot", r.reply || r.error || "", r.sources, r.file);
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify(r));
          return;
        }
        // Deterministic RAG hook for academic questions.
        let prompt = q, sources = null;
        if (ACADEMIC_RE.test(q)) {
          const k = BROAD_RE.test(q) ? 30 : RAG_TOP_K;
          const hits = await retrieveContext(q, k);
          if (hits) {
            const focused = focusHits(q, hits);
            prompt = buildGroundedPrompt(q, focused);
            sources = [...new Set(focused.map((h) => h.source))];
          }
        }
        // Path grounded: prompt sudah mandiri (konteks disuntik) -> sesi ephemeral
        // agar riwayat tak menumpuk lintas pertanyaan (penyebab context overflow).
        const sess = sources ? `rag-${Date.now()}-${Math.random().toString(36).slice(2, 8)}` : session;
        const result = await runAgent(prompt, sess);
        // Prompt grounded pakai CoT 2-langkah; tampilkan hanya bagian final "JAWABAN:".
        if (sources && result.reply) {
          const m = [...result.reply.matchAll(/jawaban\s*:/gi)].pop();
          if (m) result.reply = result.reply.slice(m.index + m[0].length).trim();
          result.sources = sources;
        }
        saveMsg(session, "user", q);
        saveMsg(session, "bot", result.reply || result.error || "", result.sources, result.file);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify(result));
      } catch (e) {
        res.writeHead(500, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: e.message }));
      }
    });
    return;
  }

  // Daftar sesi (untuk sidebar riwayat): judul = pesan user pertama.
  if (url === "/sessions") {
    const rows = db.prepare(
      `SELECT m.session AS session,
         (SELECT content FROM messages WHERE session=m.session AND role='user' ORDER BY id LIMIT 1) AS title,
         MAX(m.ts) AS last_ts, COUNT(*) AS n
       FROM messages m GROUP BY m.session ORDER BY last_ts DESC`).all();
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(rows));
    return;
  }

  // Isi satu sesi (untuk memuat ulang percakapan lama).
  if (url.startsWith("/history")) {
    const s = new URL(url, "http://x").searchParams.get("session") || "";
    const rows = db.prepare(
      "SELECT role, content, sources, file, ts FROM messages WHERE session=? ORDER BY id").all(s);
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(rows));
    return;
  }

  // Unduh dokumen yang digenerate (docx/pdf/xlsx/csv) langsung dari chat.
  if (url.startsWith("/output/")) {
    const rel = decodeURIComponent(url.split("?")[0].slice(1));
    const full = join(DTICLAW_DIR, rel);
    if (full.startsWith(OUTPUT_DIR) && existsSync(full)) {
      const name = full.split("/").pop();
      res.writeHead(200, {
        "Content-Type": MIME[extname(full).toLowerCase()] || "application/octet-stream",
        "Content-Disposition": `attachment; filename="${name}"`,
      });
      res.end(readFileSync(full));
    } else { res.writeHead(404); res.end("Not found"); }
    return;
  }

  if (url.startsWith("/healthz")) {
    fetch(`${GATEWAY_URL}/healthz`)
      .then((r) => { res.writeHead(r.status); res.end(); })
      .catch(() => { res.writeHead(502); res.end("Gateway unreachable"); });
    return;
  }

  serveStatic(req, res);
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`DTIClaw Dashboard → http://127.0.0.1:${PORT}`);
  console.log(`Gateway backend  → ${GATEWAY_URL} (agent: ${AGENT_ID}) · RAG hook ON`);
});
