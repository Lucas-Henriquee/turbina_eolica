#!/usr/bin/env bash
set -e

echo "Limpando caso OpenFOAM..."

find . -maxdepth 1 -type d -regextype posix-extended -regex '\./[0-9]+(\.[0-9]+)?' ! -path './0' -exec rm -rf {} +

rm -rf postProcessing VTK constant/polyMesh constant/extendedFeatureEdgeMesh
rm -f constant/triSurface/*.eMesh
find . -maxdepth 1 -type d -name 'processor*' -exec rm -rf {} +

rm -f 0/cellLevel 0/pointLevel 0/cellToRegion

rm -rf __pycache__
rm -f *.pyc

rm -rf runs
rm -f log.* *.foam *.OpenFOAM core core.*

echo "Limpeza concluída."