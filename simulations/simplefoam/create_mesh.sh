#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
source scripts/foam_helpers.sh

main() {
    check_environment
    print_status INFO 'OpenFOAM | steady | mesh'

    prepare_case
    create_case_mesh

    print_status DONE "Mesh ready"
    print_total_time
    print_status INFO "Open in ParaView" 'paraFoam -builtin'
    print_status INFO "Logs" 'log.*'
}

main "$@"
