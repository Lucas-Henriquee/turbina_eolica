#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
source scripts/foam_helpers.sh

main() {
    local initial_case
    if ! initial_case=$(read_initial_case "$@"); then
        print_status INFO "Usage" './run_serial.sh [--initial-case path]' >&2
        return 1
    fi
    check_environment
    print_status INFO 'OpenFOAM | serial'

    prepare_case --processes 1
    create_case_mesh --processes 1
    initialize_flow "$initial_case"
    run_solver pimpleFoam
    finish_run
}

main "$@"
