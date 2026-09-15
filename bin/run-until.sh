#!/bin/bash
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
while read -r ym; do
  DRY=0 "$HOME/PhotosBackup/bin/step3-import.sh" "$ym" || { echo "[FAIL] $ym"; exit 1; }
done < "$HOME/PhotosBackup/todo-months.txt"
echo "=== ВСЁ ==="
