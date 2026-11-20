#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
source scripts/foam_helpers.sh

main() {
    local prepare_args=()
    local settings process_count mpi_timeout

    if [ "$#" -gt 1 ]; then
        print_status FAIL "Too many arguments" >&2
        print_status INFO "Usage" './run_mpi.sh [processes]' >&2
        return 1
    fi

    # O argumento tem prioridade sobre o YAML.
    if [ "$#" -eq 1 ]; then
        prepare_args=(--processes "$1")
    fi

    check_environment
    require_commands mpirun reconstructPar timeout
    print_status INFO 'OpenFOAM | parallel'
    prepare_case "${prepare_args[@]}"

    if ! settings=$(read_parallel_settings 2> log.parallelSettings); then
        print_status FAIL "MPI settings" "log.parallelSettings" >&2
        return 1
    fi
    read -r process_count mpi_timeout <<< "$settings"
    print_status INFO "MPI processes" "$process_count"

    # Testa o MPI antes de gerar a malha.
    run_step_named "MPI preflight" mpiTest \
        timeout "${mpi_timeout}s" mpirun -np "$process_count" hostname

    create_case_mesh --processes "$process_count"
    run_step decomposePar -force
    run_step_named "Parallel mesh motion check" checkMeshMotionParallel \
        python3 scripts/check_mesh_motion.py --processes "$process_count"
    run_solver mpirun -np "$process_count" pimpleFoam -parallel

    # Reconstrói os campos antes de arquivar.
    run_step reconstructPar
    finish_run
}

main "$@"
