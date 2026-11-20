#!/usr/bin/env bash
set -euo pipefail

CASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$CASE_DIR/scripts/terminal_helpers.sh"

main() {
    local history_dir="$CASE_DIR/runs"

    if [ "$#" -ne 0 ]; then
        print_status FAIL "Unexpected arguments" >&2
        print_status INFO "Usage" './clean_runs.sh' >&2
        return 1
    fi

    print_status RUN "Remove run history" "$history_dir/"
    # A limpeza fica restrita ao histórico deste caso.
    rm -rf -- "$history_dir"
    print_status DONE "Run history removed"
}

main "$@"
