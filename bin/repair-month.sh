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
#                                       нормализует имена), нужен полный
#                                       проход месяца через import-robust.sh
#
#   repair-month.sh 2024-02
set -uo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"

ym="${1:?укажи месяц, например 2024-02}"
d="$HOME/PhotosBackup/compressed/$ym"
CHUNK="${CHUNK:-8}"
TIMEOUT="${TIMEOUT:-180}"
RETRY="${RETRY:-3}"

[ -d "$d" ] || { echo "нет папки $d — сначала пересжать месяц из originals"; exit 1; }

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

lst=$(mktemp)
osxphotos import "$d" --walk --check-not 2>/dev/null \
  | grep -E '\.(heic|mp4|mov|dng|png|webp)$' > "$lst"
n=$(wc -l < "$lst" | tr -d ' ')
echo "[$ym] нет в библиотеке: $n файлов"

if [ "$n" -gt 0 ]; then
  split -l "$CHUNK" "$lst" "${lst}-part-"
  nparts=$(ls "${lst}-part-"* | wc -l | tr -d ' ')
  i=0
  for part in "${lst}-part-"*; do
    i=$((i+1))
    restart_photos
    files=(); while IFS= read -r l; do [ -n "$l" ] && files+=("$l"); done < "$part"
    ok=0
    for attempt in $(seq 1 "$RETRY"); do
      S=$(date +%s)
      ( osxphotos import "${files[@]}" --skip-dups --dup-albums --sidecar \
          --album "Recompressed" --album "Recompressed/$ym" >/tmp/rm-out.txt 2>&1 ) &
      P=$!
      while kill -0 $P 2>/dev/null && [ $(( $(date +%s) - S )) -lt "$TIMEOUT" ]; do sleep 3; done
      if kill -0 $P 2>/dev/null; then
        kill $P 2>/dev/null
        echo "  чанк $i/$nparts: таймаут (попытка $attempt) — перезапуск Photos"
        restart_photos
      else
        wait $P 2>/dev/null; ok=1; break
      fi
    done
    if [ "$ok" = "1" ]; then
      echo "  чанк $i/$nparts за $(( $(date +%s) - S ))с — $(grep -oE 'imported [0-9]+ file groups?, [0-9]+ errors, [0-9]+ skipped' /tmp/rm-out.txt | tail -1)"
    else
      echo "  [FAIL] чанк $i/$nparts — все попытки исчерпаны"
      cat "$part" >> "$d/.failed-files"
    fi
  done
  rm -f "${lst}-part-"*
fi
rm -f "$lst"

# сверяем: уникальных файлов на диске против объектов в альбоме
uniq=$(python3 - "$d" <<'PY'
import sys, os, hashlib, collections
d = sys.argv[1]
IMG = {'.heic', '.heif', '.jpg', '.jpeg', '.png'}
VID = {'.mov', '.mp4', '.m4v'}
names = [f for f in os.listdir(d) if not f.startswith('.') and not f.endswith('.xmp')]
stems = collections.defaultdict(set)
for f in names:
    s, e = os.path.splitext(f)
    stems[s].add(e.lower())
sel = []
for f in names:
    stem, ext = os.path.splitext(f)
    if ext.lower() in VID and (stems[stem] & IMG):
        continue
    if not stem.endswith('_edited') and f'{stem}_edited' in stems:
        continue
    sel.append(os.path.join(d, f))
h = set()
for f in sel:
    m = hashlib.md5()
    with open(f, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            m.update(b)
    h.add(m.hexdigest())
print(len(h))
PY
)
have=$(osxphotos albums 2>/dev/null | grep -oE "Recompressed/$ym: [0-9]+" | grep -oE '[0-9]+$')
have=${have:-0}
echo "[$ym] уникальных файлов $uniq, в альбоме $have"

if [ "$have" -ge "$uniq" ]; then
  touch "$d/.import-complete"
  rm -f "$d/.chunk-progress" "$d/.failed-files"
  echo "[$ym] закрыт, маркер поставлен"
else
  echo "[$ym] не хватает $((uniq-have)): объекты в библиотеке есть, но не в альбоме."
  echo "      Точечно их не достать — нужен полный проход:"
  echo "        rm -f $d/.import-complete $d/.chunk-progress"
  echo "        caffeinate -ims \$HOME/PhotosBackup/bin/import-robust.sh $ym"
fi
