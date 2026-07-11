# dticlaw — Security & Correctness Audit

Auditor: Claude (atas permintaan Atok Tajuddin) · Tanggal: 2026-06-13
Scope: seluruh source `dticlaw/` (core, engines, dashboard, config). Tinjauan
statik kode (belum dijalankan). Konteks: agent lokal single-user, Node.js +
Ollama + TurboVec/ChromaDB.

## Ringkasan eksekutif

Arsitektur **bagus di atas kertas** (risk matrix, confirmation gate, network
allowlist, audit trail, dashboard localhost-only, guardian). Namun **beberapa
klaim keamanan TIDAK ditegakkan di kode** — terutama pada eksekusi tool,
kontrol akses Telegram, dan dashboard. Jangan jalankan dengan bot Telegram aktif
atau dashboard terbuka sampai temuan CRITICAL/HIGH ditambal.

| # | Severity | Komponen | Temuan |
|---|----------|----------|--------|
| 1 | 🔴 CRITICAL | core/tools.js | `exec_safe` = eksekusi shell arbitrer (`spawn(cmd,{shell:true})`) |
| 2 | 🔴 CRITICAL | core/telegram.js | Bot tanpa kontrol akses — siapa pun bisa mengendalikan agent |
| 3 | 🟠 HIGH | core/tools.js | `read_file`/`write_file` tanpa konfinemen path → path traversal |
| 4 | 🟠 HIGH | dashboard/server.js | `/api/fetch-url` SSRF — allowlist `supported` tak ditegakkan |
| 5 | 🟠 HIGH | dashboard/server.js | `/api/logs?file=` arbitrary file read (LFI) |
| 6 | 🟠 HIGH | dashboard/server.js | Tanpa autentikasi + `CORS: *` → CSRF/DNS-rebind dari web jahat |
| 7 | 🟡 MEDIUM | core/security.js | Prompt-injection guard flag-only & mudah dilewati |
| 8 | 🟡 MEDIUM | (global) | Network allowlist tidak ditegakkan global (web_fetch, research, dashboard) |
| 9 | 🟡 MEDIUM | core/gateway.js | Alur konfirmasi putus — action di-approve tak pernah dieksekusi |
| 10 | 🔵 LOW | core/risk.js | `exec_safe`/`write_file` ditandai "reversible" (salah) |
| 11 | 🔵 LOW | core/audit.js | `flush()` membuang buffer; tak ada proteksi integritas |
| 12 | 🔵 LOW | data/turbovec | `engine_state.pkl` orphan (tak dirujuk kode); `bookkb` impor pickle tak terpakai |

---

## Temuan rinci

### 1. 🔴 CRITICAL — `exec_safe` adalah eksekusi shell arbitrer
`core/tools.js:146`
```js
const child = spawn(params.command, [], { shell: true, timeout: 30000 });
```
- `shell:true` + string perintah mentah = **command injection / RCE penuh**.
  Apa pun isi `params.command` dijalankan di shell. Namanya "exec_safe" tapi
  perilakunya `exec_unrestricted` (yang justru ada di daftar `dangerous`).
- Risk matrix mengklasifikasikannya **moderate**, bukan dangerous → gate lebih longgar.
- Saat ini "diselamatkan" hanya oleh bug alur konfirmasi (temuan #9) yang tak
  pernah benar-benar mengeksekusi. Itu rapuh: satu pemanggil yang langsung
  memanggil `toolRegistry.execute()` = RCE hidup.

**Rekomendasi:** hapus `exec_safe` dari `allowed` secara default. Jika perlu,
ganti `shell:true` → `spawn(bin, argsArray, {shell:false})` dengan **allowlist
binari** (mis. hanya `ls`,`cat`,`rg`) dan tanpa interpolasi string. Pindahkan ke
kelas `dangerous`. Idealnya jalankan via sandbox (bubblewrap/firejail).

### 2. 🔴 CRITICAL — Telegram tanpa kontrol akses
`core/telegram.js` — tidak ada satu pun cek `ctx.from.id`. Semua handler
(`/research`, `/rag`, foto, teks bebas) melayani **siapa pun** yang menemukan
bot. Berarti orang asing bisa: menjalankan deep-research (fetch URL arbitrer),
query knowledge base privat, mengirim gambar untuk diproses, dan mengisi
session. AGENTS.md bilang "owner: Atok" tapi identitas pengirim tak pernah
diverifikasi.

**Rekomendasi:** allowlist `DTICLAW_OWNER_IDS` (Telegram user id). Di setiap
handler: `if (!OWNER_IDS.has(ctx.from.id)) return ctx.reply('⛔ unauthorized')`.
Tolak update dari chat grup. Pertimbangkan `bot.use()` middleware terpusat.

### 3. 🟠 HIGH — Path traversal pada read/write file
`core/tools.js:98-118` — `readFileSync(path)`/`writeFileSync(path)` memakai path
mentah tanpa konfinemen. Bisa membaca `~/.ssh/id_rsa`, `.env`, `/etc/passwd`,
atau menimpa `~/.bashrc`, config, dll.

**Rekomendasi:** definisikan `SANDBOX_ROOT` (mis. `~/dticlaw/`), lalu
`const real = realpathSync(resolve(SANDBOX_ROOT, path)); if(!real.startsWith(SANDBOX_ROOT)) throw`.
Tolak symlink keluar. Terapkan ke semua handler file.

### 4. 🟠 HIGH — SSRF pada dashboard `/api/fetch-url`
`dashboard/server.js:90-145` — array `supported` dideklarasikan tapi **tidak
pernah dipakai untuk validasi**. `fetchUrl()` mengambil URL apa pun yang dikirim
→ bisa diarahkan ke `http://169.254.169.254/...` (metadata cloud),
`http://localhost:<port>` (service internal), atau host LAN. Konten lalu di-feed
ke LLM + di-ingest (indirect prompt injection).

**Rekomendasi:** tegakkan allowlist host SEBELUM fetch; tolak IP privat/loopback
/link-local (resolve DNS dulu lalu cek rentang `10/8`,`172.16/12`,`192.168/16`,
`127/8`,`169.254/16`,`::1`,`fc00::/7`). Pakai `SecurityGuard.isAllowedOutbound`
yang sudah ada.

### 5. 🟠 HIGH — Arbitrary file read pada `/api/logs`
`dashboard/server.js:626-657`
```js
const filePath = resolve(logDir, logFile);   // logFile dari query ?file=
```
Tidak ada cek `filePath.startsWith(logDir)` (berbeda dgn `serveStatic` yang
benar). `?file=../../../../etc/passwd` → baca file arbitrer.

**Rekomendasi:** `if(!resolve(logDir,logFile).startsWith(logDir+sep)) return 403`,
dan batasi ekstensi ke `.log`/`.jsonl`.

### 6. 🟠 HIGH — Dashboard tanpa auth + CORS terbuka
`dashboard/server.js:339` `Access-Control-Allow-Origin: *` + tidak ada token/sesi.
Walau listen `127.0.0.1`, situs web jahat yang Anda buka bisa melakukan
POST ke `http://127.0.0.1:3737/api/chat` & `/api/fetch-url` (CSRF), dan dengan
CORS `*` bahkan membaca responsnya. DNS-rebinding memperparah.

**Rekomendasi:** (a) wajibkan header `Authorization: Bearer <DTICLAW_DASHBOARD_TOKEN>`
untuk semua `/api/*` non-statik; (b) set `Access-Control-Allow-Origin` ke
`http://127.0.0.1:3737` saja (bukan `*`); (c) verifikasi `Host` header =
`127.0.0.1:3737` (anti DNS-rebind); (d) tolak `req.socket.remoteAddress` non-loopback.

### 7. 🟡 MEDIUM — Prompt-injection guard lemah & flag-only
`core/security.js:22-57` — skor di atas threshold **tidak memblokir** ("Don't
block entirely — just flag"), dan bahkan tak menulis ke audit (hanya
`console.warn`). Regex sempit, mudah dilewati (unicode, parafrase, base64).

**Rekomendasi:** untuk konten EKSTERNAL (hasil fetch/RAG), terapkan kebijakan
lebih ketat + tandai ke audit; jangan mencampur konten tak tepercaya ke dalam
system prompt. Sadari guard regex hanya lapisan tipis, bukan jaminan.

### 8. 🟡 MEDIUM — Network allowlist tidak global
`isAllowedOutbound` ada tapi **tak dipanggil** sebelum `fetch` di
`tools.js` (web_fetch), `engines/deep-research` (_fetchUrl), dan dashboard.
README/AGENTS mengklaim "allowlist-only outbound" — saat ini aspiratif.

**Rekomendasi:** bungkus semua outbound lewat satu helper `safeFetch(url)` yang
memanggil `isAllowedOutbound`/anti-SSRF. Untuk research yang memang perlu URL
luas, batasi ke skema http/https + blok IP privat, dan beri sandbox jaringan.

### 9. 🟡 MEDIUM — Alur konfirmasi putus (bug fungsional)
`core/gateway.js:359-377` — `handleConfirmation` me-resolve approval dan
mengembalikan "✅ Executing: …", **tapi tak ada kode yang menjalankan action
setelah approve**. Jadi tool moderate/dangerous tak pernah benar-benar berjalan
via chat. Aman (fail-closed) tapi menyesatkan & membuat fitur tak berfungsi.

**Rekomendasi:** setelah approve, panggil `toolRegistry.execute(resolved.action)`;
sekaligus pastikan #1–#3 sudah ditambal agar eksekusi memang aman.

### 10–12. LOW
- `core/risk.js:58` menandai `exec_safe`,`write_file` sebagai reversible → bisa
  memicu auto-proceed bila impact ter-nilai "low". Hapus dari daftar reversible.
- `core/audit.js:47` `flush(){ this.buffer=[] }` membuang record (untung
  `appendFileSync` sudah menulis sinkron, jadi tak hilang — tapi buffer tak guna).
  Tak ada proteksi integritas (HMAC/append-only fs).
- `data/turbovec/engine_state.pkl` tidak dirujuk kode mana pun (orphan) →
  hapus. `engines/bookkb/bookkb.py` mengimpor `pickle` tapi tak memakainya.

---

## Status remediasi (sudah diterapkan)

| # | Temuan | Status |
|---|--------|--------|
| 1 | exec_safe RCE | ✅ DINONAKTIFKAN (`_handleExecSafe` menolak; `shell:true` dihapus) |
| 2 | Telegram tanpa auth | ✅ Telegram OFF default (web-only); butuh `DTICLAW_ENABLE_TELEGRAM=1` + owner-allowlist |
| 3 | Path traversal file | ✅ `confinePath()` mengurung read/write ke `SANDBOX_ROOT` |
| 4 | SSRF fetch-url | ✅ `assertPublicUrl()` blok IP privat/metadata + allowlist host |
| 5 | LFI /api/logs | ✅ konfinemen ke `logDir` + ekstensi `.log/.jsonl` |
| 6 | Dashboard no-auth/CORS | ✅ loopback-only + Host guard (anti DNS-rebind) + CORS same-origin |
| 7 | Prompt guard lemah | ⚠️ belum diubah (lapisan tipis; konten eksternal jangan ke system prompt) |
| 8 | Network allowlist | ✅ web_fetch kini lewat `assertPublicUrl`; research masih luas (by design) |
| 9 | Alur konfirmasi putus | ⚠️ belum (fail-closed; eksekusi tool moderate via chat tetap mati) |
| 10 | risk reversible salah | ⚠️ belum (low) |
| 12 | engine_state.pkl orphan | ✅ dihapus |

**Sandbox OS-level**: `scripts/run-sandboxed.sh` (bubblewrap) mengurung FS ke
folder dticlaw — terbukti `~/.ssh` & `.env` proyek lain TAK terlihat dari dalam.

## Postur sandboxing (untuk "berjalan di environment aman")

1. **Proses**: jalankan via `systemd --user` unit dengan
   `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ProtectHome=read-only`
   kecuali `~/dticlaw` (`ReadWritePaths`), `PrivateTmp=yes`,
   `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`, `MemoryMax`, `CPUQuota`.
2. **Jaringan**: idealnya egress filter (nftables/`firejail --netfilter`) yang
   hanya mengizinkan `127.0.0.1:11434` + host research yang disetujui.
3. **FS**: semua I/O agent dikurung ke `~/dticlaw` (lihat #3).
4. **Secrets**: `.env` `chmod 600`; jangan teruskan `DTICLAW_TELEGRAM_TOKEN`
   ke subprocess yang tak butuh (bridge mewarisi seluruh `process.env`).
5. **Node**: pertimbangkan `--experimental-permission --allow-fs-read=~/dticlaw
   --allow-fs-write=~/dticlaw --allow-child-process=false` (Node 22+) untuk
   menutup eksekusi anak & batasi FS di level runtime.

## Status klaim README vs realita

| Klaim | Realita |
|---|---|
| "Network allowlist-only outbound" | ❌ tak ditegakkan (web_fetch/research/dashboard) |
| "Risk matrix: dangerous require approval" | ⚠️ ada, tapi alur eksekusi putus & exec misklasifikasi |
| "Prompt injection guard" | ⚠️ flag-only, mudah dilewati |
| "Dashboard 127.0.0.1, never expose" | ✅ bind benar; ❌ tanpa auth + CORS `*` |
| "All data stays local / Ollama only" | ✅ untuk LLM; ⚠️ research & url-fetcher menarik dari internet (by design) |
| "Audit trail every action" | ✅ ditulis; ⚠️ injection & beberapa jalur tak teraudit |
