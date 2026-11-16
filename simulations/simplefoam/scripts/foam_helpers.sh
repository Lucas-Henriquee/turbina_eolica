#!/usr/bin/env bash

# Carrega os auxiliares do caso, inclusive nas cópias arquivadas.
FOAM_HELPER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$FOAM_HELPER_DIR/terminal_helpers.sh"
source "$FOAM_HELPER_DIR/case_helpers.sh"
source "$FOAM_HELPER_DIR/run_helpers.sh"
unset FOAM_HELPER_DIR
