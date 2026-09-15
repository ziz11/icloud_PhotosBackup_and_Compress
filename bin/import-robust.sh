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
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"

ROOT="$HOME/PhotosBackup"
CHUNK="${CHUNK:-8}"
TIMEOUT="${TIMEOUT:-180}"
RETRY="${RETRY:-3}"
# Photos переваривает примерно один чанк после старта, дальше виснет:
# в логах таймаут шёл ровно через чанк. Дешевле перезапускать его заранее
# (~28с), чем ждать таймаут 180с и потом всё равно перезапускать.
RESTART_EVERY="${RESTART_EVERY:-1}"
MIN_FREE_GB="${MIN_FREE_GB:-1}"

restart_photos() {
  pkill -f 'osxphotos import' 2>/dev/null
  sleep 1
  osascript -e 'tell application "Photos" to quit' >/dev/null 2>&1
  sleep 4
  pkill -x Photos 2>/dev/null
  sleep 3
  open -g -a Photos
  sleep 20
}

# brctl иногда отдаёт пустоту/мусор (особенно когда cloudd занят).
# Три попытки; если прочитать не вышло — возвращаем пусто, и проверка пропускается,
# чтобы не встать на ровном месте при реально свободном месте.
icloud_free_gb() {
  local out n
  for _ in 1 2 3; do
    out=$(brctl quota 2>/dev/null | head -1)
    n=$(printf '%s' "$out" | grep -oE '^[0-9]+')
    if [ -n "$n" ] && [ "$n" -gt 0 ] 2>/dev/null; then
      echo $(( n / 1073741824 )); return 0
    fi
    sleep 3
  done
  echo ""
}

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
  rm -f "/tmp/r-$ym-part-"*
  split -l "$CHUNK" "/tmp/r-$ym.lst" "/tmp/r-$ym-part-"
  nparts=$(ls "/tmp/r-$ym-part-"* | wc -l | tr -d ' ')
  echo "[$(date '+%H:%M:%S')] $ym: $total файлов, $nparts чанков (iCloud ${free} GB)"

  # прогресс по чанкам: при обрыве месяц продолжается с места, а не с начала.
  # Разбиение детерминировано (find|sort + split), поэтому номер чанка стабилен.
  prog="$d/.chunk-progress"
  from_chunk=0
  [ -f "$prog" ] && from_chunk=$(cat "$prog" 2>/dev/null | grep -oE '^[0-9]+' || echo 0)
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
      ( osxphotos import "${files[@]}" --skip-dups --dup-albums --sidecar \
          --album "Recompressed" --album "Recompressed/$ym" \
          >"/tmp/r-out.txt" 2>&1 ) &
      P=$!
      while kill -0 $P 2>/dev/null && [ $(( $(date +%s) - S )) -lt "$TIMEOUT" ]; do sleep 5; done
      if kill -0 $P 2>/dev/null; then
        kill $P 2>/dev/null
        echo "   чанк $i/$nparts: таймаут ${TIMEOUT}с (попытка $attempt) — перезапуск Photos"
        restart_photos
      else
        wait $P 2>/dev/null
        ok=1; break
      fi
    done

    chunks_done=$((chunks_done+1))
    if [ "$ok" = "1" ]; then
      # прогресс двигается ТОЛЬКО если не осталось дыр позади:
      # иначе перезапуск проскочил бы проваленные чанки навсегда
      [ "$i" -eq $((prefix+1)) ] && { prefix=$i; echo "$prefix" > "$prog"; }
      echo "   [$(date '+%H:%M:%S')] чанк $i/$nparts за $(( $(date +%s) - S ))с — $(grep -oE 'imported [0-9]+ file groups, [0-9]+ errors(, [0-9]+ skipped)?' /tmp/r-out.txt | tail -1)"
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
    echo "         Догнать: bin/retry-failed.sh $ym"
  fi
done
echo "=== очередь пройдена ==="
