#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

find_node() {
    if command -v node > /dev/null; then
        command -v node
    elif [ -x "$HOME/.local/bin/node" ]; then
        printf '%s\n' "$HOME/.local/bin/node"
    else
        echo '[FAIL] Node.js 22 or newer is required.' >&2
        return 1
    fi
}

main() {
    local node_binary
    node_binary=$(find_node)

    # Substitui o shell para encaminhar Ctrl+C ao servidor.
    exec "$node_binary" server.js
}

main "$@"
