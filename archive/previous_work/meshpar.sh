#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

load_openfoam() {
    local foam_bashrc

    if [ -n "${WM_PROJECT_DIR:-}" ]; then
        return
    fi
    foam_bashrc=$(find /usr/lib/openfoam /usr/share/openfoam \
        -path '*/etc/bashrc' -print -quit 2> /dev/null) || true
    if [ -z "$foam_bashrc" ]; then
        echo '[FAIL] OpenFOAM environment not found.' >&2
        return 1
    fi

    # O ambiente externo pode consultar variáveis ainda indefinidas.
    set +eu
    # shellcheck source=/dev/null
    source "$foam_bashrc"
    set -euo pipefail
}

run_step() {
    local command="$1" status=0
    shift

    "$command" "$@" > "log.$command" 2>&1 || status=$?
    if [ "$status" -ne 0 ]; then
        echo "[FAIL] $command. Log: log.$command" >&2
        return "$status"
    fi
    echo "[OK] $command"
}

copy_processor_surfaces() {
    local process_count="$1" index directory

    for ((index = 0; index < process_count; index++)); do
        directory="processor$index/constant/triSurface"
        mkdir -p "$directory"
        cp -r constant/triSurface/* "$directory/"
    done
}

main() {
    local process_count=6
    local mpi_binary=/usr/bin/mpirun
    local status=0 start=$SECONDS elapsed

    load_openfoam
    echo "[INFO] Historical mesh | $process_count MPI processes"

    run_step blockMesh
    run_step decomposePar -force
    copy_processor_surfaces "$process_count"

    "$mpi_binary" -np "$process_count" snappyHexMesh -overwrite -parallel \
        > log.snappyHexMesh 2>&1 || status=$?
    if [ "$status" -ne 0 ]; then
        echo '[FAIL] snappyHexMesh. Log: log.snappyHexMesh' >&2
        return "$status"
    fi
    echo '[OK] snappyHexMesh'

    # A interface AMI é criada após reconstruir a malha.
    run_step reconstructParMesh -constant
    run_step createBaffles -overwrite
    run_step checkMesh -allTopology -allGeometry

    echo '[DONE] Mesh generation complete.'
    elapsed=$((SECONDS - start))
    printf 'Total: %02d:%02d:%02d\n' \
        "$((elapsed / 3600))" "$((elapsed % 3600 / 60))" "$((elapsed % 60))"
    echo 'Logs: log.*'
}

main "$@"
