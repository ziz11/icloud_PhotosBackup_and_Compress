#!/bin/bash
# Шаг 2: сжатие выгруженных оригиналов в ~/PhotosBackup/compressed/<YYYY-MM>
# Оригиналы НЕ трогаются — читаются, результат пишется в отдельное дерево.
# Возобновляемый: готовые файлы пропускаются.
set -uo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"

ROOT="$HOME/PhotosBackup"
SRC="$ROOT/originals"
DST="$ROOT/compressed"
IMG_Q="${IMG_Q:-50}"      # HEIC качество: 50 = 2.18x @ SSIM 0.974
VID_Q="${VID_Q:-45}"      # hevc_videotoolbox q:v: 45 = 2.19x @ PSNR 36
JOBS="${JOBS:-6}"

compress_one() {
  local f="$1" ym="$2"
  local rel="${f#$SRC/$ym/}"
  local base="${rel%.*}"
  local ext="${f##*.}"
  local lower="$(echo "$ext" | tr 'A-Z' 'a-z')"
  local out

  case "$lower" in
    heic|heif|jpg|jpeg|png)
      out="$DST/$ym/$base.heic"
      [ -f "$out" ] && return 0
      mkdir -p "$(dirname "$out")"
      sips -s format heic -s formatOptions "$IMG_Q" "$f" --out "$out" >/dev/null 2>&1 \
        || { echo "ERR img $rel"; return 1; }
      # добираем метаданные, которые sips мог потерять
      exiftool -overwrite_original -TagsFromFile "$f" \
        -all:all -icc_profile "$out" >/dev/null 2>&1
      ;;
    mov|mp4|m4v)
      out="$DST/$ym/$base.mp4"
      [ -f "$out" ] && return 0
      mkdir -p "$(dirname "$out")"
      ffmpeg -y -v error -i "$f" \
        -c:v hevc_videotoolbox -q:v "$VID_Q" -tag:v hvc1 \
        -c:a copy -movflags +faststart -map_metadata 0 "$out" \
        || { echo "ERR vid $rel"; return 1; }
      ;;
    dng|cr2|nef|arw|xmp|aae)
      # RAW и сайдкары копируем как есть
      out="$DST/$ym/$rel"
      [ -f "$out" ] && return 0
      mkdir -p "$(dirname "$out")"; cp -p "$f" "$out"
      ;;
    *)
      out="$DST/$ym/$rel"
      [ -f "$out" ] && return 0
      mkdir -p "$(dirname "$out")"; cp -p "$f" "$out"
      ;;
  esac

  # страховка: если "сжатый" файл вышел больше оригинала — берём оригинал
  if [ -f "$out" ]; then
    local os ns
    os=$(stat -f '%z' "$f"); ns=$(stat -f '%z' "$out")
    if [ "$ns" -ge "$os" ]; then
      rm -f "$out"
      cp -p "$f" "$DST/$ym/$rel"
    fi
  fi
}
export -f compress_one
export SRC DST IMG_Q VID_Q

for d in "$SRC"/*/; do
  ym=$(basename "$d")
  [ -f "$d/.export-complete" ] || { echo "[skip] $ym не выгружен полностью"; continue; }
  mkdir -p "$DST/$ym"
  echo "[compress] $ym"
  find "$d" -type f ! -name '.*' -print0 \
    | xargs -0 -P "$JOBS" -I{} bash -c 'compress_one "$@"' _ {} "$ym"
  o=$(du -sk "$d" | cut -f1); n=$(du -sk "$DST/$ym" | cut -f1)
  awk -v y="$ym" -v o="$o" -v n="$n" 'BEGIN{printf "[ok] %s  %.2f GB -> %.2f GB  (%.2fx)\n", y, o/1048576, n/1048576, o/n}'
done

O=$(du -sk "$SRC" | cut -f1); N=$(du -sk "$DST" | cut -f1)
awk -v o="$O" -v n="$N" 'BEGIN{printf "=== ИТОГО %.2f GB -> %.2f GB (%.2fx, экономия %.2f GB) ===\n", o/1048576, n/1048576, o/n, (o-n)/1048576}'
