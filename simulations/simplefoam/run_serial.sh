#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
source scripts/foam_helpers.sh

main() {
    check_environment
    print_status INFO 'OpenFOAM | steady | serial'

    prepare_case --processes 1
    create_case_mesh
    run_solver simpleFoam
    finish_run
}

main "$@"
