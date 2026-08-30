#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/lib_foam.sh"

check_env

run_step blockMesh
run_step surfaceFeatureExtract
run_step snappyHexMesh -overwrite
run_step checkMesh
# run_step surfaceCheck constant/triSurface/propeller.stl

grep -E "points:|faces:|cells:|hexahedra:|polyhedra:|prisms:|propeller|cylinder|non-orthogonality|Max skewness|Mesh OK|multiply connected|Failed" log.checkMesh