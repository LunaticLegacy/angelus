#!/usr/bin/env bash
set -euo pipefail

# Build a self-contained Python executable consumed as a Tauri resource.
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="$root_dir/src-tauri/binaries"
mkdir -p "$output_dir"
data_separator="$(python -c 'import os; print(os.pathsep)')"
frontend_source="$root_dir/frontend"

# Git Bash exposes Windows drives as `/d/...`, while PyInstaller expects a
# native `D:\...` path for `--add-data` on Windows.
if [[ "${OS:-}" == "Windows_NT" ]] && command -v cygpath >/dev/null 2>&1; then
  frontend_source="$(cygpath -w "$frontend_source")"
fi

python -m PyInstaller \
  --noconfirm \
  --clean \
  --name angelus-backend \
  --onefile \
  --add-data "${frontend_source}${data_separator}frontend" \
  --collect-all angelus \
  --collect-all llmfetcher \
  "$root_dir/scripts/backend_entry.py"

backend_artifact="$root_dir/dist/angelus-backend"
backend_name="angelus-backend"
if [[ -f "${backend_artifact}.exe" ]]; then
  backend_artifact="${backend_artifact}.exe"
  backend_name="${backend_name}.exe"
fi
cp "$backend_artifact" "$output_dir/$backend_name"
chmod 755 "$output_dir/$backend_name"
