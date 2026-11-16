#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
source scripts/foam_helpers.sh

main() {
    check_environment
    print_status INFO 'OpenFOAM | mesh'

    prepare_case
    create_case_mesh

    print_status DONE "Mesh ready"
    print_total_time
    echo 'View: paraFoam -builtin'
    echo 'Logs: log.*'
}

main "$@"
