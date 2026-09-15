#!/bin/bash
# Шаг 1: выгрузка оригиналов из iCloud помесячно в ~/PhotosBackup/originals/<YYYY-MM>
# Читает только библиотеку Photos, ничего в ней не меняет.
# Возобновляемый: уже выгруженные месяцы пропускаются.
set -uo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"

ROOT="$HOME/PhotosBackup"
OUT="$ROOT/originals"
MONTHS="${1:-$ROOT/months.txt}"   # файл со списком YYYY-MM, по одному в строке
MIN_FREE_GB=25

mkdir -p "$OUT" "$ROOT/reports"

next_month() { date -j -v+1m -f '%Y-%m-%d' "$1-01" '+%Y-%m-%d'; }
free_gb() { df -g / | awk 'NR==2{print $4}'; }

while read -r ym; do
  [ -z "$ym" ] && continue
  done_flag="$OUT/$ym/.export-complete"
  if [ -f "$done_flag" ]; then
    echo "[skip] $ym уже выгружен"
    continue
  fi

  free=$(free_gb)
  if [ "$free" -lt "$MIN_FREE_GB" ]; then
    echo "[STOP] свободно ${free} GB < ${MIN_FREE_GB} GB."
    echo "       Перенеси готовые месяцы из $OUT на внешний носитель и запусти скрипт снова."
    exit 1
  fi

  from="$ym-01"; to=$(next_month "$ym")
  mkdir -p "$OUT/$ym"
  echo "[export] $ym  ($from .. $to)  свободно ${free} GB"

  osxphotos export "$OUT/$ym" \
    --from-date "$from" --to-date "$to" \
    --update --not-shared --edited-suffix '_edited' \
    --sidecar XMP \
    --report "$ROOT/reports/$ym.csv" \
    --retry 3 || { echo "[FAIL] $ym — прерываю"; exit 1; }

  touch "$done_flag"
  echo "[ok] $ym  $(du -sh "$OUT/$ym" | cut -f1)"
done < "$MONTHS"

echo "=== выгрузка завершена: $(du -sh "$OUT" | cut -f1) ==="
