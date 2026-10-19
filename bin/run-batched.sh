#!/bin/bash
# Помесячный импорт с контролем места в iCloud.
# Перед каждым месяцем смотрит остаток квоты и останавливается,
# если его меньше MIN_FREE_GB — чтобы не копить гигантскую очередь выгрузки.
#
#   run-batched.sh                 все месяцы из todo-months.txt
#   MIN_FREE_GB=2 run-batched.sh   свой порог
#   PAUSE=30 run-batched.sh        пауза между месяцами, сек
set -uo pipefail
. "$(dirname "$0")/lib.sh"

MIN_FREE_GB="${MIN_FREE_GB:-1}"
PAUSE="${PAUSE:-10}"

while read -r ym; do
  [ -z "$ym" ] && continue
  d="$ROOT/compressed/$ym"
  [ -f "$d/.import-complete" ] && { echo "[skip] $ym"; continue; }

  free=$(icloud_free_gb)
  if [ -z "$free" ]; then
    echo "   (квоту iCloud прочитать не удалось — проверку места пропускаю)"
  elif [ "$free" -lt "$MIN_FREE_GB" ]; then
    echo "[STOP] в iCloud свободно ${free} GB (порог ${MIN_FREE_GB})."
    echo "       Удали старые объекты в Photos, очисти «Недавно удалённые»,"
    echo "       затем запусти этот скрипт снова — он продолжит с $ym."
    exit 2
  fi

  echo "[$(date '+%H:%M:%S')] $ym — старт (iCloud свободно ${free} GB)"
  DRY=0 "$ROOT/bin/step3-import.sh" "$ym" 2>&1 | grep -E 'imported|error' | tail -1
  if [ ! -f "$d/.import-complete" ]; then
    echo "[FAIL] $ym — прерываю, маркер не создан"
    exit 1
  fi
  echo "[$(date '+%H:%M:%S')] $ym — готово"
  sleep "$PAUSE"
done < "$ROOT/todo-months.txt"

echo "=== очередь пройдена ==="
