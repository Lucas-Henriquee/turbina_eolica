#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/lib_foam.sh"

check_env

NP="${1:-$(( $(nproc) / 2 ))}"
[ "$NP" -lt 1 ] && NP=1

echo "  windTurbineCase  —  paralelo  (${NP} processos MPI)"
echo ""

sed -i -E "s/(numberOfSubdomains[[:space:]]+)[0-9]+;/\1${NP};/" system/decomposeParDict

run_step blockMesh
run_step surfaceFeatureExtract
run_step snappyHexMesh -overwrite
run_step createBaffles -overwrite
run_step checkMesh

rm -f 0/cellLevel 0/pointLevel 0/cellToRegion

run_step decomposePar -force

run_solver_parallel "${NP}"

archive_run