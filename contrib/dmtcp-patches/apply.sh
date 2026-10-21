#!/usr/bin/env bash
set -euo pipefail
mana_root="$(cd "$(dirname "$0")/../.." && pwd)"
patch="$mana_root/contrib/dmtcp-patches/0001-ipc-skip-socket-scan-when-PMI_FD-is-set.patch"
source_file="$mana_root/dmtcp/src/plugin/ipc/socket/socketconnlist.cpp"
[[ -f "$source_file" ]] || { echo "ERROR: initialize the DMTCP submodule first" >&2; exit 1; }
if git -C "$mana_root/dmtcp" apply --reverse --check "$patch" 2>/dev/null; then
  echo "PMI_FD compatibility patch is already applied."
  exit 0
fi
git -C "$mana_root/dmtcp" apply --check "$patch"
git -C "$mana_root/dmtcp" apply "$patch"
git -C "$mana_root/dmtcp" diff --check
echo "Applied $patch to the local DMTCP submodule checkout."
echo "The bundled DMTCP checkout now includes the local Hydra compatibility change."
