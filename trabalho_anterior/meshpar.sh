#!/bin/bash
set -e

# Ambiente minimo do OpenFOAM para utilitarios como blockMesh encontrarem etc/controlDict
export WM_PROJECT_DIR=/usr/share/openfoam
export FOAM_ETC=/usr/share/openfoam/etc

# Se houver bashrc funcional, carrega configuracoes adicionais (nao obrigatorio)
if [ -f /usr/share/openfoam/etc/bashrc ] && [ -x /usr/share/openfoam/bin/foamEtcFile ]; then
	# shellcheck source=/usr/share/openfoam/etc/bashrc
	source /usr/share/openfoam/etc/bashrc
fi

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
decomposePar -force > log.decomposePar

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