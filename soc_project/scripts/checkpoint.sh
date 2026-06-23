#!/usr/bin/env bash
# ============================================================
#  checkpoint.sh  —  Buat restore point untuk project SOC
# ------------------------------------------------------------
#  Membuat "restore point" berupa commit + annotated tag.
#  Menangkap DUA repo sekaligus:
#    1. SOC_Local        (config, docker-compose, scripts, dashboards grafana, dll)
#    2. soc-dashboard    (repo terpisah milik kolaborator — commit & tag LOKAL saja)
#
#  Pakai:
#    ./checkpoint.sh "deskripsi singkat perubahan"
#    ./checkpoint.sh                 # deskripsi default = "manual"
#
#  File besar (logs/, .venv, *.zip, Model_Chatbot/) tidak ikut
#  karena sudah diatur di .gitignore.
# ============================================================
set -euo pipefail

# --- warna ---
c_g='\033[0;32m'; c_y='\033[1;33m'; c_b='\033[0;34m'; c_r='\033[0;31m'; c_0='\033[0m'
info(){ echo -e "${c_b}==>${c_0} $*"; }
ok(){   echo -e "${c_g}  ✓${c_0} $*"; }
warn(){ echo -e "${c_y}  !${c_0} $*"; }

# --- lokasi repo ---
REPO_ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
DASH="$REPO_ROOT/soc_project/soc-dashboard"

# --- argumen ---
DESC="${*:-manual}"
TS="$(date +%Y%m%d-%H%M%S)"
# slug: lowercase, non-alnum -> '-', rapikan
SLUG="$(echo "$DESC" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//' | cut -c1-40)"
[ -z "$SLUG" ] && SLUG="manual"
TAG="checkpoint/${TS}-${SLUG}"

# checkpoint_repo <dir> <label> <msg> <tag>
checkpoint_repo(){
  local dir="$1" label="$2" msg="$3" tag="$4"
  [ -d "$dir/.git" ] || { warn "$label: bukan repo git, dilewati ($dir)"; return 0; }
  (
    cd "$dir"
    git add -A
    if git diff --cached --quiet; then
      warn "$label: tidak ada perubahan baru — tag menandai HEAD saat ini"
    else
      git commit -q -m "checkpoint: $msg"
      ok "$label: commit baru $(git rev-parse --short HEAD)"
    fi
    if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
      warn "$label: tag '$tag' sudah ada, dilewati"
    else
      git tag -a "$tag" -m "$msg"
      ok "$label: tag $tag -> $(git rev-parse --short HEAD)"
    fi
  )
}

echo ""
info "Membuat restore point: ${c_y}$TAG${c_0}"
echo -e "    deskripsi: $DESC"
echo ""

checkpoint_repo "$REPO_ROOT" "SOC_Local"     "$DESC" "$TAG"
checkpoint_repo "$DASH"      "soc-dashboard" "$DESC" "$TAG"

echo ""
ok "Restore point selesai."
echo -e "    Lihat semua : ${c_b}./restore.sh --list${c_0}"
echo -e "    Restore ke  : ${c_b}./restore.sh $TAG${c_0}"
echo ""
