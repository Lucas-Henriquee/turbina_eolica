#!/usr/bin/env bash

archive_failed_run() {
    local status="${1:-failed}" log_name="${2:-pimpleFoam}" destination
    if ! destination=$(python3 scripts/archive_case.py --status "$status" 2> log.archive); then
        print_status FAIL "Archive" "Check log.archive and runs/." >&2
        return 1
    fi
    cp -- "$destination/config.txt" config.txt
    print_status INFO "Saved" "${destination#"$PWD"/}" >&2
    print_status INFO "Log" "${destination#"$PWD"/}/logs/log.$log_name" >&2
}

run_solver() {
    local log=log.pimpleFoam start=$SECONDS status=0
    print_status RUN "pimpleFoam" "$log"
    # Isola o grupo para encerrar todos os processos MPI.
    setsid "$@" > "$log" 2>&1 &
    local solver_pid=$!

    cleanup_solver() {
        trap - INT TERM
        kill -TERM -- "-${solver_pid}" 2> /dev/null || true
        sleep 2
        kill -KILL -- "-${solver_pid}" 2> /dev/null || true
        wait "$solver_pid" 2> /dev/null || true
        print_status STOP "Simulation interrupted" >&2
        archive_failed_run interrupted pimpleFoam || true
        exit 130
    }

    trap cleanup_solver INT TERM
    wait "$solver_pid" || status=$?
    trap - INT TERM
    if [ "$status" -ne 0 ]; then
        print_status FAIL "pimpleFoam" "exit $status" >&2
        archive_failed_run failed pimpleFoam || true
        exit "$status"
    fi
    print_status OK "pimpleFoam" "$((SECONDS - start))s"
}

update_analysis_status() {
    python3 scripts/run_state.py analysis-status "$1" "$2"
}

finish_run() {
    local destination status=0 start=$SECONDS
    if ! destination=$(python3 scripts/archive_case.py --status completed 2> log.archive); then
        print_status FAIL "Archive" "Check log.archive and runs/." >&2
        return 1
    fi
    local relative_destination="${destination#"$PWD"/}"
    print_status OK "Archive" "$relative_destination"
    # Usa os scripts arquivados.
    python3 "$destination/postprocessing/calculate_energy.py" \
        --case "$destination" \
        > "$destination/logs/log.calculate_energy" 2>&1 || status=$?
    if [ "$status" -eq 0 ] \
        && plots_enabled "$destination/metadata/resolved_config.json" \
            2>> "$destination/logs/log.calculate_energy"; then
        python3 "$destination/postprocessing/plot_results.py" \
            --case "$destination" \
            > "$destination/logs/log.plot_results" 2>&1 || status=$?
    fi
    update_analysis_status "$destination/run_status.json" "$status"
    bash "$destination/scripts/collect_config.sh" \
        --case "$destination" \
        > "$destination/logs/log.collectConfig" 2>&1 || status=$?
    if [ "$status" -eq 0 ]; then
        cp -- "$destination/config.txt" config.txt
    else
        update_analysis_status "$destination/run_status.json" "$status"
    fi
    if [ "$status" -ne 0 ]; then
        print_status FAIL "Post-processing" "exit $status" >&2
        print_status INFO "Logs" "$relative_destination/logs/" >&2
        return "$status"
    fi
    print_status OK "Post-processing" "$((SECONDS - start))s"
    python3 "$destination/scripts/show_results.py" \
        --case "$destination" \
        > "$destination/logs/log.summary" 2>&1
    print_status DONE "Simulation complete"
    print_total_time
    print_status INFO "Results" "$relative_destination/results/"
    print_status INFO "Logs" "$relative_destination/logs/"
}
