#!/usr/bin/env bash
set -euo pipefail

# Build a self-contained Python executable consumed as a Tauri resource.
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="$root_dir/src-tauri/binaries"
mkdir -p "$output_dir"

python -m PyInstaller \
  --noconfirm \
  --clean \
  --name angelus-backend \
  --onefile \
  --add-data "$root_dir/frontend:frontend" \
  --collect-all angelus \
  --collect-all llmfetcher \
  "$root_dir/scripts/backend_entry.py"

cp "$root_dir/dist/angelus-backend" "$output_dir/angelus-backend"
chmod 755 "$output_dir/angelus-backend"
