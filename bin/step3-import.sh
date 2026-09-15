#!/bin/bash
# Шаг 3: импорт сжатых файлов обратно в Photos.
# Создаёт НОВЫЕ объекты; старые надо удалять вручную в Photos.
#
# Каждый файл кладётся в ДВА альбома:
#   Recompressed            — плоский, всё новое разом. Нужен, чтобы потом
#                             умным альбомом «альбом — не Recompressed»
#                             выделить всё старое одним списком.
#   Recompressed/<YYYY-MM>  — помесячно, для навигации.
#
# Использование:
#   step3-import.sh            все месяцы
#   step3-import.sh 2023       только 2023
#   step3-import.sh 2023-07    один месяц
set -uo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"

ROOT="$HOME/PhotosBackup"
DST="$ROOT/compressed"
FILTER="${1:-}"
DRY="${DRY:-1}"     # DRY=0 чтобы реально импортировать

for d in "$DST"/${FILTER}*/; do
  [ -d "$d" ] || { echo "нет папок по фильтру '$FILTER'"; exit 1; }
  ym=$(basename "$d")
  [ -f "$d/.import-complete" ] && { echo "[skip] $ym уже импортирован"; continue; }
  echo "[import] $ym"

  args=(
    "$d"
    --walk
    --skip-dups
    --sidecar                     # XMP рядом: дата, GPS, ключевые слова, заголовок
    --album "Recompressed"        # плоский — всё новое
    --album "Recompressed/$ym"    # помесячный
    --report "$ROOT/reports/import-$ym.csv"
  )
  [ "$DRY" = "1" ] && args+=(--dry-run)

  osxphotos import "${args[@]}" || { echo "[FAIL] $ym"; exit 1; }
  [ "$DRY" = "1" ] || touch "$d/.import-complete"
done

if [ "$DRY" = "1" ]; then
  echo
  echo "Это был DRY-RUN. Ничего не импортировано."
  echo "Реальный запуск: DRY=0 $0 ${FILTER}"
fi
