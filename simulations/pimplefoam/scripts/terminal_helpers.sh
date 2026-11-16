#!/usr/bin/env bash

CASE_START_SECONDS=$SECONDS

print_total_time() {
    local elapsed=$((SECONDS - CASE_START_SECONDS))
    printf 'Total:   %02d:%02d:%02d\n' \
        "$((elapsed / 3600))" "$((elapsed % 3600 / 60))" "$((elapsed % 60))"
}

print_status() {
    local status="$1" label="$2" detail="${3:-}"
    if [ -n "$detail" ]; then
        printf '%-6s %-24s %s\n' "[$status]" "$label" "$detail"
    else
        printf '%-6s %s\n' "[$status]" "$label"
    fi
}

require_commands() {
    local command
    for command in "$@"; do
        if ! command -v "$command" > /dev/null; then
            print_status FAIL "Missing command" "$command" >&2
            return 1
        fi
    done
}

run_step_named() {
    local label="$1" log_name="$2" start=$SECONDS status=0
    shift 2
    {
        printf 'Command:'
        printf ' %q' "$@"
        printf '\n\n'
        "$@"
    } > "log.${log_name}" 2>&1 || status=$?
    if [ "$status" -eq 0 ]; then
        print_status OK "$label" "$((SECONDS - start))s"
    else
        print_status FAIL "$label" "exit $status" >&2
        archive_failed_run failed "$log_name" || true
        exit "$status"
    fi
}

run_step() {
    local command="$1"
    shift
    run_step_named "$command" "$command" "$command" "$@"
}
