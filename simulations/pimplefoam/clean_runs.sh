#!/usr/bin/env bash
set -euo pipefail

CASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

main() {
    local history_dir="$CASE_DIR/runs"

    if [ "$#" -ne 0 ]; then
        echo 'Usage: ./clean_runs.sh' >&2
        return 1
    fi

    echo "[RUN] Remove run history: $history_dir/"
    # A limpeza fica restrita ao histórico deste caso.
    rm -rf -- "$history_dir"
    echo '[DONE] Run history removed.'
}

main "$@"
