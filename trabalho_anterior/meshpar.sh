#!/bin/bash

# Ambiente minimo do OpenFOAM para utilitarios como blockMesh encontrarem etc/controlDict
set +e
# Carrega o ambiente completo do OpenFOAM
FOAM_BASHRC=$(find /usr/lib/openfoam /usr/share/openfoam -name bashrc 2>/dev/null | head -1)
if [ -z "$FOAM_BASHRC" ]; then
    echo "❌ OpenFOAM bashrc não encontrado!"
    exit 1
fi
source "$FOAM_BASHRC"
echo "✅ OpenFOAM carregado de: $FOAM_BASHRC"
set -e

# --- CONFIGURAÇÕES RYZEN 5 5600G ---
NP=6
MPI_EXEC="/usr/bin/mpirun"

echo "-----------------------------------"
echo "🏗️  Gerando Malha com $NP processadores"
echo "-----------------------------------"

echo "🧱 1. blockMesh"
blockMesh > log.blockMesh

# --- PULANDO SURFACE FEATURES (Incompatível com v2412 sem ajuste de Dict) ---
# echo "🧩 2. surfaceFeatures"
# surfaceFeatures > log.surfaceFeatures

echo "✂️  3. Decompondo para snappyHexMesh"
decomposePar -force > log.decomposePar 2>&1

echo "📁 3.5 Copiando geometrias STL para processadores"
for i in $(seq 0 $((NP-1))); do
    mkdir -p processor${i}/constant/triSurface
    cp -r constant/triSurface/* processor${i}/constant/triSurface/
done

echo "🔷 4. snappyHexMesh (Paralelo)"
# Sem a flag --use-hwthread-cpus para evitar warnings
$MPI_EXEC -np $NP snappyHexMesh -overwrite -parallel > log.snappyHexMesh

echo "📦 5. Reconstruindo malha (Necessário para criar AMI)"
reconstructParMesh -constant > log.reconstructParMesh

echo "🔄 6. Criando Interface Rotativa (AMI)"
createBaffles -overwrite > log.createBaffles

# Opcional: Checagem rápida
echo "✅ 7. checkMesh"
checkMesh -allTopology -allGeometry > log.checkMesh

echo "🏁 Malha pronta."