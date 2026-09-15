#!/bin/bash
# Импорт одного месяца чанками.
# Photos отваливается по AppleScript (-128) на больших пачках, поэтому
# файлы отдаются порциями по CHUNK штук.
#
#   import-month.sh 2021-09
#   CHUNK=100 import-month.sh 2021-09
set -uo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"

ROOT="$HOME/PhotosBackup"
ym="$1"
d="$ROOT/compressed/$ym"
CHUNK="${CHUNK:-150}"
RETRY="${RETRY:-2}"

[ -d "$d" ] || { echo "нет папки $d"; exit 1; }
[ -f "$d/.import-complete" ] && { echo "[skip] $ym"; exit 0; }

# список медиафайлов (без сайдкаров — их osxphotos подтянет сам)
find "$d" -type f ! -name '*.xmp' ! -name '.*' | sort > "/tmp/im-$ym.lst"
total=$(wc -l < "/tmp/im-$ym.lst" | tr -d ' ')
echo "[$ym] файлов: $total, чанк: $CHUNK"

split -l "$CHUNK" "/tmp/im-$ym.lst" "/tmp/im-$ym-part-"
i=0; nparts=$(ls "/tmp/im-$ym-part-"* | wc -l | tr -d ' ')
fails=0

for part in "/tmp/im-$ym-part-"*; do
  i=$((i+1))
  ok=0
  for attempt in $(seq 1 "$RETRY"); do
    files=()
    while IFS= read -r line; do files+=("$line"); done < "$part"
    if osxphotos import "${files[@]}" \
         --skip-dups --sidecar \
         --album "Recompressed" --album "Recompressed/$ym" \
         >"/tmp/im-$ym-out.txt" 2>&1; then
      ok=1; break
    fi
    echo "   чанк $i/$nparts — попытка $attempt не удалась, жду 15 сек"
    sleep 15
  done
  if [ "$ok" = "1" ]; then
    res=$(grep -oE 'imported [0-9]+ file groups, [0-9]+ errors(, [0-9]+ skipped)?' "/tmp/im-$ym-out.txt" | tail -1)
    echo "   [$(date '+%H:%M:%S')] чанк $i/$nparts — $res"
  else
    echo "   [FAIL] чанк $i/$nparts"
    tail -3 "/tmp/im-$ym-out.txt" | sed 's/^/      /'
    fails=$((fails+1))
  fi
done

rm -f "/tmp/im-$ym-part-"*
if [ "$fails" = "0" ]; then
  touch "$d/.import-complete"
  echo "[$ym] готово"
else
  echo "[$ym] сбойных чанков: $fails — маркер не ставлю"
  exit 1
fi
