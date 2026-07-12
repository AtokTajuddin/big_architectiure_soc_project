# Sistem Checkpoint / Restore Point — Project SOC

Alat sederhana untuk membuat **restore point** sebelum/selama upgrade pipeline,
supaya kalau ada yang rusak di tengah jalan bisa balik ke titik aman.

## Konsep

- 1 checkpoint = 1 **commit + annotated tag** bernama `checkpoint/<waktu>-<slug>`.
- Menangkap **2 repo** sekaligus:
  - `SOC_Local` — config, `docker-compose.yml`, scripts, dashboards Grafana, policies, dll.
  - `soc-dashboard` — repo terpisah (milik kolaborator); di-commit & tag **lokal saja**, tidak di-push.
- File berat **tidak ikut** (sudah di `.gitignore`): `logs/` (15GB), `.venv`, `*.zip`, `Model_Chatbot/` (23GB).

## Pemakaian

Jalankan dari folder `soc_project/scripts/`:

```bash
cd soc_project/scripts

# Buat restore point
./checkpoint.sh "sebelum upgrade suricata ke v8"

# Lihat semua restore point
./restore.sh --list

# Kembali ke salah satu restore point
./restore.sh checkpoint/20260623-2010-sebelum-upgrade-suricata-ke-v8
```

## Keamanan restore

`restore.sh` **tidak pernah menghilangkan pekerjaan** secara permanen:

1. Sebelum mengembalikan, state saat ini otomatis disimpan jadi tag
   `safety/<waktu>-pre-restore` di kedua repo.
2. Baru kemudian `git reset --hard` ke checkpoint tujuan.
3. Mau maju lagi ke kondisi sebelum restore? Jalankan:
   `./restore.sh safety/<waktu>-pre-restore`

Selain itu semua perpindahan tetap tercatat di `git reflog` (cadangan terakhir).

## Alur kerja yang disarankan saat improvement

```bash
./checkpoint.sh "baseline sebelum mulai"   # titik aman awal
# ... kerjakan upgrade pipeline ...
./checkpoint.sh "suricata v8 jalan"        # tandai milestone yang sukses
# ... lanjut, ternyata rusak ...
./restore.sh checkpoint/...-suricata-v8-jalan   # balik ke milestone tadi
```

## Backup darurat .git

Saat setup, `.git` dibersihkan dari ~29GB sampah. Cadangan history asli ada di:
`../SOC_Local_git-backup_*/` (berisi `soc-history.bundle` + `dotgit-clean.tar.gz`).
Restore manual bila perlu: `git clone soc-history.bundle <folder-baru>`.
