#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

main() {
    echo '[RUN] Remove generated case files.'

    find . -maxdepth 1 -type d -regextype posix-extended \
        -regex './[0-9]+([.][0-9]+)?' \
        ! -name '0' -exec rm -rf -- {} +

    # run.sh restaura os campos a partir de 0.orig ou zero.org.
    rm -rf -- 0 processor* postProcessing constant/polyMesh
    rm -f -- log.*

    echo '[DONE] Case cleaned.'
}

main "$@"
