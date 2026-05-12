#!/bin/bash

echo "🧹 Limpando o caso..."

# 1. Remove pastas de tempo (resultados numéricos: 0.01, 1, 2, 10...)
# O comando ignora pastas que não são números
ls -1 | grep -E '^[0-9]+(\.[0-9]+)?$' | grep -v '^0$' | xargs rm -rf

# 2. Remove pasta 0 (será restaurada do 0.orig pelo run.sh)
rm -rf 0

# 3. Remove pastas de processadores (paralelização)
rm -rf processor*

# 4. Remove logs de execução
rm -rf log.*

# 5. Remove pós-processamento (se houver)
rm -rf postProcessing

# 6. (Opcional) Remove a malha gerada para forçar recriação
# Se você quiser manter a malha e só limpar os resultados, comente a linha abaixo
rm -rf constant/polyMesh

echo "✨ Tudo limpo! Pronto para rodar de novo."