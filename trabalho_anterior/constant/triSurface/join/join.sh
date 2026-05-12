#!/bin/bash
# ## --- USER INPUTS --- ##

# Nome do arquivo STL combinado de saída
target="outerCylinder.stl"

# Lista de arquivos STL a serem combinados
inputStlFileList=("inlet.stl" "outlet.stl" "walls.stl")

# Lista de nomes de superfície/patches
outSurfaceNameList=("inlet" "outlet" "walls")

# ## --- END USER INPUTS --- ##

# Apaga arquivo de saída antigo, se existir
[ -f "$target" ] && rm "$target"

# Cria novo arquivo STL de saída
touch "$target"

# Obtém o número de arquivos
length=${#inputStlFileList[@]}

for (( j=0; j<length; j++ )); do
    inputFile="${inputStlFileList[$j]}"
    surfaceName="${outSurfaceNameList[$j]}"
    
    echo "Processando '$inputFile' como '$surfaceName'"

    # Criar arquivo temporário
    tempFile=$(mktemp)

    # Substitui a linha do 'solid' e do 'endsolid' com o nome da superfície
    sed "s/^solid.*/solid $surfaceName/" "$inputFile" | sed "s/^endsolid.*/endsolid $surfaceName/" > "$tempFile"

    # Anexa ao arquivo final
    cat "$tempFile" >> "$target"

    # Remove temporário
    rm "$tempFile"
done

echo "Arquivo combinado gerado: $target"
