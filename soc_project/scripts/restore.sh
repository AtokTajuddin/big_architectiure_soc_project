#!/usr/bin/env bash
# ============================================================
#  restore.sh  —  Kembali ke restore point (checkpoint)
# ------------------------------------------------------------
#  Pakai:
#    ./restore.sh --list            # tampilkan semua restore point
#    ./restore.sh <tag>             # kembali ke restore point tsb
#    ./restore.sh <tag> --yes       # tanpa konfirmasi
#
#  AMAN: sebelum mengembalikan, state SAAT INI otomatis disimpan
#  jadi tag 'safety/<waktu>-pre-restore' di kedua repo, sehingga
#  Anda selalu bisa maju lagi:  ./restore.sh safety/<waktu>-pre-restore
#
#  Mengembalikan DUA repo: SOC_Local + soc-dashboard (jika tag-nya ada).
#  Memakai 'git reset --hard' (tetap bisa dibatalkan lewat tag safety
#  atau 'git reflog').
# ============================================================
set -euo pipefail

c_g='\033[0;32m'; c_y='\033[1;33m'; c_b='\033[0;34m'; c_r='\033[0;31m'; c_0='\033[0m'
info(){ echo -e "${c_b}==>${c_0} $*"; }
ok(){   echo -e "${c_g}  ✓${c_0} $*"; }
warn(){ echo -e "${c_y}  !${c_0} $*"; }
err(){  echo -e "${c_r}  ✗${c_0} $*" >&2; }

REPO_ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
DASH="$REPO_ROOT/soc_project/soc-dashboard"

# --- daftar restore point ---
list_points(){
  echo ""
  info "Restore point di SOC_Local (terbaru di atas):"
  echo ""
  git -C "$REPO_ROOT" for-each-ref --sort=-creatordate \
    --format='  %(refname:short)%09%(creatordate:short)  %(subject)' \
    refs/tags/checkpoint refs/tags/safety 2>/dev/null || true
  echo ""
  echo -e "  Restore: ${c_b}./restore.sh <tag>${c_0}"
  echo ""
}

# checkpoint_repo <dir> <label> <msg> <tag>  (simpan state saat ini)
save_safety(){
  local dir="$1" label="$2" tag="$3"
  [ -d "$dir/.git" ] || return 0
  (
    cd "$dir"
    git add -A
    git diff --cached --quiet || git commit -q -m "safety: auto-save sebelum restore"
    git rev-parse -q --verify "refs/tags/$tag" >/dev/null || git tag -a "$tag" -m "auto-save sebelum restore"
  )
  ok "$label: state saat ini disimpan -> $tag"
}

# reset_repo <dir> <label> <tag>
reset_repo(){
  local dir="$1" label="$2" tag="$3"
  [ -d "$dir/.git" ] || { warn "$label: bukan repo git, dilewati"; return 0; }
  (
    cd "$dir"
    if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
      git reset --hard "$tag" >/dev/null
      ok "$label: dikembalikan ke $tag ($(git rev-parse --short HEAD))"
    else
      warn "$label: tidak punya tag '$tag' — repo ini dibiarkan apa adanya"
    fi
  )
}

# --- argumen ---
if [ $# -eq 0 ] || [ "${1:-}" = "--list" ] || [ "${1:-}" = "-l" ]; then
  list_points
  exit 0
fi

TARGET="$1"; shift || true
ASSUME_YES="no"
[ "${1:-}" = "--yes" ] || [ "${1:-}" = "-y" ] && ASSUME_YES="yes"

# validasi tag ada di repo utama
if ! git -C "$REPO_ROOT" rev-parse -q --verify "refs/tags/$TARGET" >/dev/null; then
  err "Restore point '$TARGET' tidak ditemukan di SOC_Local."
  list_points
  exit 1
fi

echo ""
warn "Akan mengembalikan working tree ke: ${c_y}$TARGET${c_0}"
warn "Perubahan setelah titik itu akan dilepas dari branch (tetap tersimpan di tag safety)."
if [ "$ASSUME_YES" != "yes" ]; then
  read -r -p "Lanjutkan? [y/N] " ans
  case "$ans" in y|Y|yes|YES) ;; *) echo "Dibatalkan."; exit 0;; esac
fi

SAFE_TS="$(date +%Y%m%d-%H%M%S)"
SAFETY="safety/${SAFE_TS}-pre-restore"

echo ""
info "1) Menyimpan state saat ini (jaring pengaman)"
save_safety "$REPO_ROOT" "SOC_Local"     "$SAFETY"
save_safety "$DASH"      "soc-dashboard" "$SAFETY"

echo ""
info "2) Mengembalikan ke $TARGET"
reset_repo "$REPO_ROOT" "SOC_Local"     "$TARGET"
reset_repo "$DASH"      "soc-dashboard" "$TARGET"

echo ""
ok "Selesai. Untuk membatalkan (maju lagi ke state tadi):"
echo -e "    ${c_b}./restore.sh $SAFETY${c_0}"
echo ""
