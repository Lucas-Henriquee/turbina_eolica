#!/usr/bin/env bash

read_parallel_settings() {
    python3 scripts/run_state.py parallel
}

plots_enabled() {
    python3 scripts/run_state.py plots "$1"
}

check_environment() {
    if [ -z "${WM_PROJECT_DIR:-}" ]; then
        print_status FAIL "OpenFOAM not loaded" >&2
        echo 'Run: source /usr/lib/openfoam/openfoam2512/etc/bashrc' >&2
        return 1
    fi
    require_commands \
        python3 setsid blockMesh surfaceFeatureExtract snappyHexMesh \
        createBaffles topoSet createPatch checkMesh pimpleFoam \
        surfaceInertia surfaceCheck mergeOrSplitBaffles moveDynamicMesh

    if ! python3 -c 'import yaml, numpy, matplotlib' > log.dependencies 2>&1; then
        print_status FAIL "Python dependencies" "log.dependencies" >&2
        echo 'Run from repository root: python3 -m pip install -r requirements.txt' >&2
        return 1
    fi
    # Preserva resultados existentes.
    if [ -d postProcessing ] \
        || [ -d constant/polyMesh ] \
        || compgen -G 'processor[0-9]*' > /dev/null \
        || [ -n "$(find . -maxdepth 1 -type d -regextype posix-extended \
            -regex '\./[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?' \
            ! -path './0' -print -quit)" ]; then
        print_status FAIL "Existing mesh or results" >&2
        echo 'Run: python3 scripts/archive_case.py --status interrupted' >&2
        return 1
    fi
}

prepare_case() {
    run_step_named "Prepare case" prepareCase \
        python3 scripts/prepare_case.py "$@"
    run_step_named "Configuration report" collectConfig \
        bash scripts/collect_config.sh
}

create_case_mesh() {
    run_step blockMesh
    run_step surfaceFeatureExtract
    run_step snappyHexMesh -overwrite
    run_step createBaffles -overwrite
    # Desacopla os pontos dos lados fixo e rotativo da AMI.
    run_step mergeOrSplitBaffles -split -overwrite
    run_step topoSet
    run_step createPatch -overwrite
    # Os campos precisam conhecer o patch recém-criado.
    run_step_named "Refresh fields" prepareFields \
        python3 scripts/prepare_case.py
    run_step checkMesh
    if ! grep -q 'Mesh OK' log.checkMesh; then
        print_status FAIL "Mesh validation" >&2
        archive_failed_run failed checkMesh || true
        exit 1
    fi
    run_step_named "Mesh motion check" checkMeshMotion python3 scripts/check_mesh_motion.py
    rm -f \
        0/cellLevel 0/pointLevel 0/cellToRegion \
        0/nSurfaceLayers 0/thickness 0/thicknessFraction
}
