#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/lib_foam.sh"

check_env

run_step blockMesh
run_step surfaceFeatureExtract
run_step snappyHexMesh -overwrite
run_step checkMesh