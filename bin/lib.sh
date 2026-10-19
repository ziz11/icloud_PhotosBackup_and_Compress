# Общие функции скриптов импорта. Подключение:
#   . "$(dirname "$0")/lib.sh"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"

ROOT="$HOME/PhotosBackup"
BIN="$ROOT/bin"

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

# import_chunk <месяц> <таймаут, с> <лог> <файлы...>
# Код возврата: 0 — ок, 1 — osxphotos сообщил об ошибке, 2 — таймаут (процесс убит).
import_chunk() {
  local ym="$1" timeout="$2" log="$3" start p
  shift 3
  start=$(date +%s)
  osxphotos import "$@" --skip-dups --dup-albums --sidecar \
    --album "Recompressed" --album "Recompressed/$ym" >"$log" 2>&1 &
  p=$!
  while kill -0 "$p" 2>/dev/null && [ $(( $(date +%s) - start )) -lt "$timeout" ]; do
    sleep 1
  done
  if kill -0 "$p" 2>/dev/null; then
    kill "$p" 2>/dev/null; wait "$p" 2>/dev/null
    return 2
  fi
  wait "$p" || return 1
  # osxphotos может выйти с 0, даже если часть файлов не встала
  grep -qE ', [1-9][0-9]* errors?' "$log" && return 1
  return 0
}

import_summary() {
  grep -oE 'imported [0-9]+ file groups?, [0-9]+ errors?(, [0-9]+ skipped)?' "$1" | tail -1
}
