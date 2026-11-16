#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

main() {
    # Aceita arquivo de saída e --case; a leitura fica no Python.
    python3 "$SCRIPT_DIR/config_report.py" "$@"
}

main "$@"
