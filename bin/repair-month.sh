#!/bin/bash
# Точечная починка месяца: заливает только то, чего нет в библиотеке,
# не гоняя месяц целиком.
#
# Photos переваривает примерно один чанк после запуска, дальше виснет,
# поэтому перед каждым чанком он перезапускается, и на чанк даётся 3 попытки.
#
# Дыры бывают двух видов:
#   1) файла нет в библиотеке        -> --check-not его назовёт, заливаем
#   2) объект есть, но не в альбоме  -> поимённо не определить (Photos
#                                       нормализует имена), нужен fix-album.py
#                                       или полный проход import-robust.sh
#
#   repair-month.sh 2024-02
set -uo pipefail
. "$(dirname "$0")/lib.sh"

ym="${1:?укажи месяц, например 2024-02}"
d="$ROOT/compressed/$ym"
CHUNK="${CHUNK:-8}"
TIMEOUT="${TIMEOUT:-180}"
RETRY="${RETRY:-3}"
LOG="/tmp/rm-out.txt"

[ -d "$d" ] || { echo "нет папки $d — сначала пересжать месяц из originals"; exit 1; }

lst=$(mktemp)
# любые медиа, включая оригиналы (jpg, mov, RAW…), положенные как есть,
# когда сжатие не дало выигрыша
osxphotos import "$d" --walk --check-not 2>/dev/null \
  | grep -iE '\.(heic|heif|jpe?g|png|gif|webp|mp4|mov|m4v|dng|cr2|nef|arw)$' > "$lst"
n=$(wc -l < "$lst" | tr -d ' ')
echo "[$ym] нет в библиотеке: $n файлов"

if [ "$n" -gt 0 ]; then
  split -a 4 -l "$CHUNK" "$lst" "${lst}-part-"
  nparts=$(ls "${lst}-part-"* | wc -l | tr -d ' ')
  i=0
  for part in "${lst}-part-"*; do
    i=$((i+1))
    restart_photos
    files=(); while IFS= read -r l; do [ -n "$l" ] && files+=("$l"); done < "$part"
    ok=0
    for attempt in $(seq 1 "$RETRY"); do
      S=$(date +%s)
      import_chunk "$ym" "$TIMEOUT" "$LOG" "${files[@]}"
      case $? in
        0) ok=1; break ;;
        2) echo "  чанк $i/$nparts: таймаут (попытка $attempt) — перезапуск Photos"
           restart_photos ;;
        *) echo "  чанк $i/$nparts: ошибка импорта (попытка $attempt): $(import_summary "$LOG")"
           sleep 5 ;;
      esac
    done
    if [ "$ok" = "1" ]; then
      echo "  чанк $i/$nparts за $(( $(date +%s) - S ))с — $(import_summary "$LOG")"
    else
      echo "  [FAIL] чанк $i/$nparts — все попытки исчерпаны"
      cat "$part" >> "$d/.failed-files"
    fi
  done
  rm -f "${lst}-part-"*
fi
rm -f "$lst"

# сверяем: уникальных файлов на диске против объектов в альбоме
uniq=$(python3 "$(dirname "$0")/photolib.py" uniq "$d") || { echo "не удалось посчитать файлы"; exit 1; }
have=$(osxphotos albums 2>/dev/null | grep -oE "Recompressed/$ym: [0-9]+" | grep -oE '[0-9]+$')
have=${have:-0}
echo "[$ym] уникальных файлов $uniq, в альбоме $have"

if [ "$have" -ge "$uniq" ]; then
  touch "$d/.import-complete"
  rm -f "$d/.chunk-progress" "$d/.failed-files"
  echo "[$ym] закрыт, маркер поставлен"
else
  echo "[$ym] не хватает $((uniq-have)): объекты в библиотеке есть, но не в альбоме."
  echo "      Точечно: $BIN/fix-album.py $ym"
  echo "      Или полный проход:"
  echo "        rm -f $d/.import-complete $d/.chunk-progress"
  echo "        caffeinate -ims $BIN/import-robust.sh $ym"
fi
