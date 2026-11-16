#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
temporary_file=''

cleanup() {
    if [ -n "$temporary_file" ]; then
        rm -f -- "$temporary_file"
    fi
}

main() {
    local output_file=outerCylinder.stl
    local input_files=(inlet.stl outlet.stl walls.stl)
    local surface_names=(inlet outlet walls)
    local index input_file

    for input_file in "${input_files[@]}"; do
        if [ ! -f "$input_file" ]; then
            echo "[FAIL] Missing STL: $input_file" >&2
            return 1
        fi
    done

    # Substitui a saída apenas após combinar todas as superfícies.
    temporary_file=$(mktemp "${output_file}.XXXXXX")
    trap cleanup EXIT

    {
        for index in "${!input_files[@]}"; do
            printf 'Input: %s | surface: %s\n' \
                "${input_files[index]}" "${surface_names[index]}"
            sed \
                -e "s/^solid.*/solid ${surface_names[index]}/" \
                -e "s/^endsolid.*/endsolid ${surface_names[index]}/" \
                "${input_files[index]}" >> "$temporary_file"
        done
    } > log.joinStl 2>&1

    mv -- "$temporary_file" "$output_file"
    temporary_file=''
    echo "[DONE] Combined STL: $output_file"
    echo 'Log: log.joinStl'
}

main "$@"
