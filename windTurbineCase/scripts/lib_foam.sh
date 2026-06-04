#!/usr/bin/env bash

# check_env
#   Verifica se o ambiente do OpenFOAM foi carregado.
check_env() {
    if [ -z "${WM_PROJECT_DIR:-}" ]; then
        echo "ERRO: ambiente do OpenFOAM não detectado." >&2
        echo "" >&2
        echo "Carregue o OpenFOAM antes de executar este script:" >&2
        echo "  source /caminho/para/openfoam/etc/bashrc" >&2
        echo "" >&2
        echo "Para localizar o caminho no seu sistema:" >&2
        echo "  find /usr/lib /opt ~/OpenFOAM -name 'bashrc' 2>/dev/null | grep -i openfoam" >&2
        exit 1
    fi
}

# run_step <comando> [args...]
#   Executa um utilitário OpenFOAM salvando a saída em log.<comando>.
run_step() {
    local cmd="$1"; shift
    local log="log.${cmd}"

    printf "  %-30s " "${cmd} $*"

    if "${cmd}" "$@" > "${log}" 2>&1; then
        echo "OK  →  ${log}"
    else
        echo "FALHOU"
        tail -20 "${log}" >&2
        archive_failed_run
        clean_case_root
        exit 1
    fi
}

clean_case_root() {
    find . -maxdepth 1 -type d -regextype posix-extended \
        -regex '\./[0-9]+(\.[0-9]+)?' \
        ! -path './0' \
        -exec rm -rf {} +

    rm -rf postProcessing VTK logs results
    rm -rf constant/polyMesh constant/extendedFeatureEdgeMesh
    rm -f constant/triSurface/*.eMesh

    rm -rf processor*
    rm -rf __pycache__

    rm -f 0/cellLevel 0/pointLevel 0/cellToRegion
    rm -f *.pyc *.foam *.OpenFOAM core core.*
}

next_run_dir() {
    local prefix="${1:-test}"
    local timestamp
    timestamp=$(date +"%Y%m%d_%H%M%S")

    mkdir -p runs

    local last_id
    last_id=$(find runs -maxdepth 1 -type d -name "${prefix}[0-9][0-9][0-9]_*" \
        | sed -E "s/.*${prefix}([0-9]{3})_.*/\1/" \
        | sort -n \
        | tail -1)

    local next_id
    if [ -z "${last_id}" ]; then
        next_id=1
    else
        next_id=$((10#${last_id} + 1))
    fi

    local run_id
    run_id=$(printf "%s%03d" "${prefix}" "${next_id}")

    echo "runs/${run_id}_${timestamp}"
}

archive_run() {
    local run_dir
    run_dir=$(next_run_dir "test")

    mkdir -p "${run_dir}/logs"
    mkdir -p "${run_dir}/constant"

    mkdir -p "${run_dir}/system"
    cp -f system/controlDict "${run_dir}/system/" 2>/dev/null || true

    if [ -x "./scripts/collect_config.sh" ]; then
        ./scripts/collect_config.sh "${run_dir}/config.txt" 2>/dev/null || true
    else
        echo "Aviso: collect_config.sh não encontrado." > "${run_dir}/config.txt"
    fi

    mv -f log.* "${run_dir}/logs/" 2>/dev/null || true

    find . -maxdepth 1 -type d -regextype posix-extended \
        -regex '\./[0-9]+(\.[0-9]+)?' \
        ! -path './0' \
        -exec mv {} "${run_dir}/" \;

    mv -f postProcessing "${run_dir}/" 2>/dev/null || true
    mv -f VTK "${run_dir}/" 2>/dev/null || true

    if [ -d constant/polyMesh ]; then
        mv constant/polyMesh "${run_dir}/constant/"
    fi

    touch "${run_dir}/$(basename "${run_dir}").foam"

    clean_case_root

    echo "  Resultado disponível em:"
    echo "  ParaView: ${run_dir}/$(basename "${run_dir}").foam"
}

archive_failed_run() {
    local fail_dir
    fail_dir=$(next_run_dir "failed")

    mkdir -p "${fail_dir}/logs"

    if [ -x "./scripts/collect_config.sh" ]; then
        ./scripts/collect_config.sh "${fail_dir}/config.txt" 2>/dev/null || true
    else
        echo "Aviso: collect_config.sh não encontrado." > "${fail_dir}/config.txt"
    fi

    mkdir -p "${fail_dir}/constant"

    if [ -d constant/polyMesh ]; then
        mv constant/polyMesh "${fail_dir}/constant/"
    fi

    mv -f log.* "${fail_dir}/logs/" 2>/dev/null || true

    echo ""
    echo "  Execução interrompida/falhou."
    echo "  Logs salvos em: ${fail_dir}/logs/"
}

run_solver_serial() {
    local log="log.pimpleFoam"

    echo ""
    echo "  pimpleFoam  (serial)"
    echo "  log completo: ${log}"
    echo ""

    local start
    start=$(date +%s)

    setsid pimpleFoam > "${log}" 2>&1 &
    local solver_pid=$!

    cleanup_serial() {
        echo ""
        echo "Interrompendo pimpleFoam..."

        trap - INT TERM

        kill -TERM -- "-${solver_pid}" 2>/dev/null || true
        sleep 2
        kill -KILL -- "-${solver_pid}" 2>/dev/null || true

        archive_failed_run
        clean_case_root

        exit 130
    }

    trap cleanup_serial INT TERM

    set +e
    wait "${solver_pid}"
    local status=$?
    set -e

    trap - INT TERM

    if [ "${status}" -eq 0 ]; then
        local end
        end=$(date +%s)
        local elapsed=$((end - start))
    else
        echo ""
        echo "  ERRO: pimpleFoam encerrou com código ${status}." >&2
        echo "  Últimas linhas de ${log}:" >&2
        tail -30 "${log}" >&2

        archive_failed_run
        clean_case_root

        exit "${status}"
    fi

    echo "  solver concluído  →  ${log}"
    echo "  tempo total: ${elapsed} s"
    echo ""
}

run_solver_parallel() {
    local np="$1"
    local log="log.pimpleFoam"

    echo ""
    echo "  pimpleFoam  (paralelo, ${np} processos)"
    echo "  log completo: ${log}"
    echo ""

    local start
    start=$(date +%s)

    # Testa primeiro se o MPI consegue iniciar.
    if ! timeout 10s mpirun -np "${np}" hostname > log.mpiTest 2>&1; then

        echo ""
        echo "  ERRO: MPI não conseguiu iniciar com ${np} processos." >&2
        echo "  Últimas linhas de log.mpiTest:" >&2
        tail -30 log.mpiTest >&2

        archive_failed_run
        clean_case_root

        exit 1
    fi

    # Roda o solver
    setsid mpirun -np "${np}" pimpleFoam -parallel > "${log}" 2>&1 &
    local mpi_pid=$!

    cleanup_mpi() {
        echo ""
        echo "Interrompendo execução paralela..."

        trap - INT TERM

        kill -TERM -- "-${mpi_pid}" 2>/dev/null || true
        sleep 2
        kill -KILL -- "-${mpi_pid}" 2>/dev/null || true

        archive_failed_run
        clean_case_root

        exit 130
    }

    trap cleanup_mpi INT TERM

    set +e
    wait "${mpi_pid}"
    local status=$?
    set -e

    trap - INT TERM

    if [ "${status}" -eq 0 ]; then

        local end
        end=$(date +%s)
        local elapsed=$((end - start))
    else

        echo ""
        echo "  ERRO: pimpleFoam paralelo encerrou com código ${status}." >&2
        echo "  Últimas linhas de ${log}:" >&2
        tail -30 "${log}" >&2

        archive_failed_run
        clean_case_root

        exit "${status}"
    fi

    printf "  %-30s " "reconstructPar"

    if reconstructPar > log.reconstructPar 2>&1; then
        echo "OK  →  log.reconstructPar"
    else

        echo "FALHOU" >&2
        tail -20 log.reconstructPar >&2

        archive_failed_run
        clean_case_root

        exit 1
    fi

    rm -rf processor*

    echo "  solver concluído  →  ${log}"
    echo "  tempo total: ${elapsed} s"
    echo ""
}