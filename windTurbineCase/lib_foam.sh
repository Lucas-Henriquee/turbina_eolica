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
        echo "" >&2
        echo "Últimas linhas de ${log}:" >&2
        tail -20 "${log}" >&2
        exit 1
    fi
}

#   Lê endTime do controlDict e imprime o valor.
_read_end_time() {
    awk '/^[[:space:]]*endTime[[:space:]]+/ {gsub(";","",$2); print $2; exit}' system/controlDict
}

#   Executa pimpleFoam serial com monitor de progresso.
run_solver_serial() {
    local log="log.pimpleFoam"

    echo ""
    echo "  pimpleFoam  (serial)"
    echo "  log completo: ${log}"
    echo ""

    local start
    start=$(date +%s)

    trap '
        echo ""
        echo "Interrompendo pimpleFoam..."
        pkill -P $$ 2>/dev/null || true
        exit 130
    ' INT TERM

    if pimpleFoam > "${log}" 2>&1; then
        local end
        end=$(date +%s)
        local elapsed=$((end - start))

        echo "  solver concluído  →  ${log}"
        echo "  tempo total: ${elapsed} s"
        echo ""
    else
        local status=$?
        echo ""
        echo "  ERRO: pimpleFoam encerrou com código ${status}." >&2
        echo "  Últimas linhas de ${log}:" >&2
        tail -30 "${log}" >&2
        exit "${status}"
    fi
}

#   Executa pimpleFoam via MPI com monitor de progresso 
run_solver_parallel() {
    local np="$1"
    local log="log.pimpleFoam"

    echo ""
    echo "  pimpleFoam  (paralelo, ${np} processos)"
    echo "  log completo: ${log}"
    echo ""

    local start
    start=$(date +%s)

    trap '
    echo ""
    echo "Interrompendo MPI..."

    pkill -P $$ 2>/dev/null || true
    kill 0 2>/dev/null || true
    pkill -9 pimpleFoam 2>/dev/null || true
    pkill -9 mpirun 2>/dev/null || true

    exit 130
    ' INT TERM

    if mpirun -np "${np}" pimpleFoam -parallel > "${log}" 2>&1; then
        local end
        end=$(date +%s)
        local elapsed=$((end - start))

        echo "  solver concluído  →  ${log}"
        echo "  tempo total: ${elapsed} s"
        echo ""
    else
        local status=$?
        echo ""
        echo "  ERRO: pimpleFoam paralelo encerrou com código ${status}." >&2
        echo "  Últimas linhas de ${log}:" >&2
        tail -30 "${log}" >&2
        exit "${status}"
    fi

    printf "  %-30s " "reconstructPar"
    if reconstructPar > log.reconstructPar 2>&1; then
        echo "OK  →  log.reconstructPar"
    else
        echo "FALHOU" >&2
        tail -20 log.reconstructPar >&2
        exit 1
    fi
    rm -rf processor*
    echo ""
}

#   Move log.* para runs/ para manter o diretório do caso limpo.
archive_logs() {
    mkdir -p runs
    mv -f log.* runs/ 2>/dev/null || true
    echo "  logs arquivados em runs/"
}