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
    local label="$1" log_file="$2" status=0
    shift 2

    "$@" > "$log_file" 2>&1 || status=$?
    if [ "$status" -ne 0 ]; then
        echo "[FAIL] $label. Log: $log_file" >&2
        return "$status"
    fi
    echo "[OK] $label"
}

clear_previous_results() {
    # Preserva as cópias dos campos iniciais.
    rm -rf -- processor* postProcessing
    rm -f -- log.* *.log core core.* *.foam
    find . -maxdepth 1 -type d -regextype posix-extended \
        -regex './[0-9]+([.][0-9]+)?' \
        ! -name '0' ! -name '0.orig' -exec rm -rf -- {} +
}

restore_initial_fields() {
    if [ ! -d 0 ] && [ -d 0.orig ]; then
        cp -r 0.orig 0
    elif [ ! -d 0 ] && [ -d zero.org ]; then
        cp -r zero.org 0
    fi
}

main() {
    local process_count=6
    local mpi_binary=/usr/bin/mpirun
    local solver=pimpleFoam
    local start=$SECONDS elapsed

    load_openfoam
    echo "[INFO] Historical case | $process_count MPI processes"

    clear_previous_results
    restore_initial_fields
    run_step decomposePar log.decomposePar decomposePar -force

    # Preserva a saída completa do solver.
    echo "[RUN] $solver. Log: log.pimpleFoam"
    run_step "$solver" log.pimpleFoam \
        "$mpi_binary" --oversubscribe -np "$process_count" "$solver" -parallel
    run_step reconstructPar log.reconstructPar reconstructPar

    echo '[DONE] Simulation complete.'
    elapsed=$((SECONDS - start))
    printf 'Total: %02d:%02d:%02d\n' \
        "$((elapsed / 3600))" "$((elapsed % 3600 / 60))" "$((elapsed % 60))"
    echo 'Logs: log.*'
}

main "$@"
