#!/usr/bin/env bash
# Uji menyeluruh DTIClaw via /chat. Simpan tiap respons ke responses/.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESP="$DIR/responses"; mkdir -p "$RESP"
CHAT="http://127.0.0.1:3737/chat"
SUMMARY="$DIR/SUMMARY.md"
echo "# DTIClaw — Hasil Uji Menyeluruh" > "$SUMMARY"
echo "" >> "$SUMMARY"
echo "Model otak: $(grep -oE 'ollama/[a-z0-9.:_-]+' "$DIR/../.dticlaw-state/openclaw.json" | head -1) · $(date '+%Y-%m-%d %H:%M')" >> "$SUMMARY"
echo "" >> "$SUMMARY"

run() {  # $1=id $2=pertanyaan
  local id="$1" q="$2"
  local t0=$(date +%s)
  curl -s --max-time 580 -X POST "$CHAT" -H "Content-Type: application/json" \
    -d "$(python3 -c 'import json,sys;print(json.dumps({"message":sys.argv[1],"session":sys.argv[2]}))' "$q" "test_$id")" \
    > "$RESP/$id.json" 2>&1
  local dur=$(( $(date +%s) - t0 ))
  local reply src
  reply=$(python3 -c "import json;d=json.load(open('$RESP/$id.json'));print(d.get('reply') or ('ERROR: '+str(d.get('error'))))" 2>/dev/null)
  src=$(python3 -c "import json;d=json.load(open('$RESP/$id.json'));print(', '.join(d.get('sources') or []))" 2>/dev/null)
  {
    echo "## [$id] $q"
    echo ""
    echo "- Durasi: ${dur}s${src:+ · Sumber: $src}"
    echo ""
    echo '```'
    echo "$reply"
    echo '```'
    echo ""
  } >> "$SUMMARY"
  echo "[$id] done ${dur}s"
}

run identity        "Halo, perkenalkan dirimu singkat."
run jadwal_awanA    "Kapan saja jadwal Teknologi Komputasi Awan kelas A?"
run dosen_ridho     "Siapa dosen Ridho Rahman Hariadi dan apa bidangnya?"
run abstain         "Siapa presiden pertama Republik Indonesia?"
run jadwal_kelasA   "Sebutkan seluruh mata kuliah kelas A beserta hari dan jamnya."
run kalender        "Kapan jadwal UTS menurut kalender akademik?"
echo "=== SELESAI. Lihat $SUMMARY ==="
