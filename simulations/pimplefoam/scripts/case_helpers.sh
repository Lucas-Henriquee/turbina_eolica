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
        print_status INFO "Locate OpenFOAM" \
            "find /usr/lib/openfoam /opt -ipath '*/openfoam*/etc/bashrc' 2>/dev/null" >&2
        print_status INFO "Load the returned path" 'source "/path/to/openfoam/etc/bashrc"' >&2
        return 1
    fi
    require_commands \
        python3 setsid blockMesh surfaceFeatureExtract snappyHexMesh \
        createBaffles topoSet createPatch checkMesh pimpleFoam \
        surfaceInertia surfaceCheck mergeOrSplitBaffles moveDynamicMesh

    if ! python3 -c 'import yaml, numpy, matplotlib' > log.dependencies 2>&1; then
        print_status FAIL "Python dependencies" "log.dependencies" >&2
        print_status INFO "Install from repo root" 'python3 -m pip install -r requirements.txt' >&2
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
        print_status INFO "Archive existing run" 'python3 scripts/archive_case.py --status interrupted' >&2
        return 1
    fi
}

prepare_case() {
    run_step_named "Prepare case" prepareCase \
        python3 scripts/prepare_case.py "$@"
    run_step_named "Configuration report" collectConfig \
        bash scripts/collect_config.sh
}

read_initial_case() {
    if [ "$#" -eq 0 ]; then
        return 0
    fi
    if [ "$#" -ne 2 ] || [ "$1" != --initial-case ] || [ -z "$2" ]; then
        print_status FAIL "Expected --initial-case <SimpleFoam case>" >&2
        return 1
    fi

    local source_case
    if ! source_case=$(cd -- "$2" 2>/dev/null && pwd -P) ||
        [ "$source_case" = "$(pwd -P)" ] ||
        [ ! -d "$source_case/constant/polyMesh" ]; then
        print_status FAIL "Invalid initial flow case" "$2" >&2
        return 1
    fi
    require_commands mapFields foamListTimes foamDictionary || return 1
    printf '%s\n' "$source_case"
}

map_initial_flow() (
    local source_case="$1" source_time field staging
    local fields=(U p k omega nut)

    source_time=$(foamListTimes -case "$source_case" -latestTime -noZero) || exit
    if [ -z "$source_time" ]; then
        printf 'No computed time found in %s.\n' "$source_case" >&2
        exit 1
    fi
    for field in "${fields[@]}"; do
        if [ ! -f "$source_case/$source_time/$field" ] &&
            [ ! -f "$source_case/$source_time/$field.gz" ]; then
            printf 'Missing source field %s at %s.\n' "$field" "$source_time" >&2
            exit 1
        fi
    done

    # Mantém a malha e o estado do rotor fora do mapeamento.
    staging=$(mktemp -d) || exit
    trap 'rm -rf -- "$staging"' EXIT
    mkdir "$staging/0" || exit
    cp -a system "$staging/system" || exit
    foamDictionary -entry writeCompression -set off "$staging/system/controlDict" || exit
    ln -s "$PWD/constant" "$staging/constant" || exit
    for field in "${fields[@]}"; do cp "0/$field" "$staging/0/" || exit; done

    cat > "$staging/system/mapFieldsDict" <<'EOF' || exit
FoamFile
{
    version 2.0;
    format ascii;
    class dictionary;
    object mapFieldsDict;
}
patchMap ();
cuttingPatches (AMI1 AMI2);
EOF
    mapFields -case "$staging" -sourceTime "$source_time" "$source_case" || exit
    for field in "${fields[@]}"; do
        if [ ! -s "$staging/0/$field" ]; then
            printf 'Field %s was not mapped.\n' "$field" >&2
            exit 1
        fi
    done
    for field in "${fields[@]}"; do cp "$staging/0/$field" "0/$field" || exit; done
)

initialize_flow() {
    if [ -n "$1" ]; then
        run_step_named "Initialize flow" mapFields map_initial_flow "$1"
    fi
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
        python3 scripts/prepare_case.py "$@"
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
