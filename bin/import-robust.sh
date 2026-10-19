#!/bin/bash
# Импорт месяцев с восстановлением после зависаний Photos.
#
# Photos перестаёт принимать импорт после того, как его несколько раз
# прибили по таймауту AppleScript. Лечится перезапуском приложения,
# поэтому здесь: таймаут на чанк -> убить osxphotos -> перезапустить
# Photos -> повторить. Плюс профилактический перезапуск каждые RESTART_EVERY чанков.
#
#   import-robust.sh 2025-01         все незалитые месяцы по 2025-01 включительно
#   import-robust.sh                 все незалитые месяцы
#   CHUNK=50 import-robust.sh 2025-01   размер чанка
set -uo pipefail
. "$(dirname "$0")/lib.sh"

CHUNK="${CHUNK:-8}"
TIMEOUT="${TIMEOUT:-180}"
RETRY="${RETRY:-3}"
# Photos переваривает примерно один чанк после старта, дальше виснет:
# в логах таймаут шёл ровно через чанк. Дешевле перезапускать его заранее
# (~28с), чем ждать таймаут 180с и потом всё равно перезапускать.
RESTART_EVERY="${RESTART_EVERY:-1}"
MIN_FREE_GB="${MIN_FREE_GB:-1}"
LOG="/tmp/r-out.txt"

chunks_done=0

# Верхняя граница: аргумент, переменная UNTIL или всё подряд.
# Список месяцев берётся из самой папки compressed, а не из внешнего файла,
# чтобы не гонять по устаревшему todo-months.txt.
UNTIL="${1:-${UNTIL:-9999-99}}"
months=$(for d in "$ROOT/compressed"/*/; do
           m=$(basename "$d")
           [ "$m" \> "$UNTIL" ] && continue
           [ -f "$d/.import-complete" ] && continue
           echo "$m"
         done | sort)
if [ -z "$months" ]; then echo "нечего делать: всё по $UNTIL уже залито"; exit 0; fi
echo "цель: по $UNTIL включительно; месяцев в очереди: $(echo "$months" | wc -l | tr -d ' ')"

for ym in $months; do
  d="$ROOT/compressed/$ym"
  [ -f "$d/.import-complete" ] && { echo "[skip] $ym"; continue; }

  free=$(icloud_free_gb)
  if [ -z "$free" ]; then
    echo "   (квоту iCloud прочитать не удалось — проверку места пропускаю)"
    free="?"
  elif [ "$free" -lt "$MIN_FREE_GB" ]; then
    echo "[STOP] в iCloud свободно ${free} GB (порог ${MIN_FREE_GB})."
    echo "       Освободи место и запусти снова — продолжит с $ym."
    exit 2
  fi

  find "$d" -type f ! -name '*.xmp' ! -name '.*' | sort > "/tmp/r-$ym.lst"
  total=$(wc -l < "/tmp/r-$ym.lst" | tr -d ' ')
  if [ "$total" -eq 0 ]; then
    touch "$d/.import-complete"; echo "[$ym] пустой — отмечен"; continue
  fi
  rm -f "/tmp/r-$ym-part-"*
  # -a 4: у BSD split суффиксов aa..zz хватает только на 676 чанков
  split -a 4 -l "$CHUNK" "/tmp/r-$ym.lst" "/tmp/r-$ym-part-"
  nparts=$(ls "/tmp/r-$ym-part-"* | wc -l | tr -d ' ')
  echo "[$(date '+%H:%M:%S')] $ym: $total файлов, $nparts чанков (iCloud ${free} GB)"

  # прогресс по чанкам: при обрыве месяц продолжается с места, а не с начала.
  # Разбиение детерминировано (find|sort + split), поэтому номер чанка стабилен.
  prog="$d/.chunk-progress"
  from_chunk=0
  [ -f "$prog" ] && from_chunk=$(grep -oE '^[0-9]+' "$prog" 2>/dev/null || echo 0)
  [ "$from_chunk" -gt 0 ] && echo "   продолжаю с чанка $((from_chunk+1)) (перемотка пропущена)"

  i=0; fails=0
  prefix="$from_chunk"   # до какого чанка идёт НЕПРЕРЫВНАЯ цепочка успехов
  failed_list="$d/.failed-files"
  for part in "/tmp/r-$ym-part-"*; do
    i=$((i+1))
    [ "$i" -le "$from_chunk" ] && continue
    if [ "$chunks_done" -gt 0 ] && [ $((chunks_done % RESTART_EVERY)) -eq 0 ]; then
      echo "   профилактический перезапуск Photos"
      restart_photos
    fi

    files=(); while IFS= read -r l; do files+=("$l"); done < "$part"
    ok=0
    for attempt in $(seq 1 "$RETRY"); do
      S=$(date +%s)
      import_chunk "$ym" "$TIMEOUT" "$LOG" "${files[@]}"
      case $? in
        0) ok=1; break ;;
        2) echo "   чанк $i/$nparts: таймаут ${TIMEOUT}с (попытка $attempt) — перезапуск Photos"
           restart_photos ;;
        *) echo "   чанк $i/$nparts: ошибка импорта (попытка $attempt): $(import_summary "$LOG")"
           sleep 5 ;;
      esac
    done

    chunks_done=$((chunks_done+1))
    if [ "$ok" = "1" ]; then
      # прогресс двигается ТОЛЬКО если не осталось дыр позади:
      # иначе перезапуск проскочил бы проваленные чанки навсегда
      [ "$i" -eq $((prefix+1)) ] && { prefix=$i; echo "$prefix" > "$prog"; }
      echo "   [$(date '+%H:%M:%S')] чанк $i/$nparts за $(( $(date +%s) - S ))с — $(import_summary "$LOG")"
    else
      echo "   [FAIL] чанк $i/$nparts — файлы записаны в $failed_list"
      cat "$part" >> "$failed_list"
      fails=$((fails+1))
    fi
  done

  rm -f "/tmp/r-$ym-part-"*
  if [ "$fails" = "0" ]; then
    rm -f "$prog" "$failed_list"
    touch "$d/.import-complete"
    echo "[$(date '+%H:%M:%S')] $ym готов"
  else
    echo "[$ym] сбойных чанков: $fails — маркер не ставлю."
    echo "         Проваленные файлы: $failed_list ($(wc -l < "$failed_list" | tr -d ' ') шт)"
    echo "         Догнать: bin/repair-month.sh $ym"
  fi
done
echo "=== очередь пройдена ==="
