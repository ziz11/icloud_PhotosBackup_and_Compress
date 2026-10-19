#!/bin/bash
# Повторный экспорт уже выгруженных месяцев (доливка нового).
#
# Отличия от step1-export.sh:
#   - игнорирует .export-complete, то есть работает по месяцам, которые
#     уже помечены выгруженными;
#   - исключает объекты из альбомов Recompressed и Recompressed/<месяц>
#     (ранние месяцы есть только в помесячном). Это сжатые копии,
#     залитые обратно шагом 3. Без фильтра они попали бы в originals
#     и на следующем прогоне сжались бы второй раз.
#
# Удаление из библиотеки на бэкап не влияет: --cleanup не используется,
# --update только добавляет и обновляет файлы.
#
# Использование:
#   step1-refresh.sh 2026-08
#   step1-refresh.sh 2026-06 2026-07 2026-08
set -uo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"

ROOT="$HOME/PhotosBackup"
OUT="$ROOT/originals"
MIN_FREE_GB=25

[ $# -gt 0 ] || { echo "нужен хотя бы один месяц в формате YYYY-MM"; exit 1; }

next_month() { date -j -v+1m -f '%Y-%m-%d' "$1-01" '+%Y-%m-%d'; }
free_gb() { df -g / | awk 'NR==2{print $4}'; }

for ym in "$@"; do
  case "$ym" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]) ;;
    *) echo "[skip] '$ym' не похоже на YYYY-MM"; continue ;;
  esac

  free=$(free_gb)
  if [ "$free" -lt "$MIN_FREE_GB" ]; then
    echo "[STOP] свободно ${free} GB < ${MIN_FREE_GB} GB."
    exit 1
  fi

  from="$ym-01"; to=$(next_month "$ym")
  before=$(find "$OUT/$ym" -type f ! -name '.*' 2>/dev/null | wc -l | tr -d ' ')
  mkdir -p "$OUT/$ym"
  echo "[refresh] $ym  ($from .. $to)  было $before файлов, свободно ${free} GB"

  osxphotos export "$OUT/$ym" \
    --from-date "$from" --to-date "$to" \
    --update --not-shared --edited-suffix '_edited' \
    --query-eval "not any(a == 'Recompressed' or a.startswith('Recompressed/') for a in photo.albums)" \
    --sidecar XMP \
    --report "$ROOT/reports/$ym.csv" \
    --retry 3 || { echo "[FAIL] $ym — прерываю"; exit 1; }

  after=$(find "$OUT/$ym" -type f ! -name '.*' | wc -l | tr -d ' ')
  touch "$OUT/$ym/.export-complete"
  echo "[ok] $ym  $before -> $after файлов  $(du -sh "$OUT/$ym" | cut -f1)"
done
