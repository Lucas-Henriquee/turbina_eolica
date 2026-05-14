#!/usr/bin/env bash
set -euo pipefail

export WM_PROJECT_DIR=/usr/share/openfoam
export FOAM_ETC=/usr/share/openfoam/etc

if [ -f /usr/share/openfoam/etc/bashrc ] && [ -x /usr/share/openfoam/bin/foamEtcFile ]; then
  # shellcheck source=/usr/share/openfoam/etc/bashrc
  source /usr/share/openfoam/etc/bashrc
fi

NP=6
MPI_EXEC="/usr/bin/mpirun"
MPI_FLAGS="--oversubscribe"
SOLVER="pimpleFoam"

LOG_KEY="log.simulation_solidBody"
LOG_INTERVAL_SEC=5

echo "Iniciando simulacao"

echo "Limpando caso"
rm -rf processor* postProcessing
rm -f log.* *.log core core.* *.foam

# Remove pastas de tempo numericas, incluindo 0.x, preservando 0 e 0.orig
find . -maxdepth 1 -type d -regextype posix-extended \
  -regex './[0-9]+([.][0-9]+)?' \
  ! -name '0' ! -name '0.orig' -print0 | xargs -0r rm -rf

if [ ! -d "0" ] && [ -d "0.orig" ]; then
  echo "Restaurando pasta 0 a partir de 0.orig"
  cp -r 0.orig 0
fi

if [ ! -d "0" ] && [ -d "zero.org" ]; then
  echo "Restaurando pasta 0 a partir de zero.org"
  cp -r zero.org 0
fi

echo "Decompondo para $NP processos"
decomposePar -copyZero -force > log.decompose 2>&1


echo "Rodando $SOLVER em paralelo..."
$MPI_EXEC $MPI_FLAGS -np "$NP" "$SOLVER" -parallel 2>&1 \
  | stdbuf -oL -eL awk -v s="$LOG_INTERVAL_SEC" '
      BEGIN { t = systime() }

      # Só o que é realmente crítico passa sempre
      /FOAM FATAL ERROR|FOAM FATAL|SIGFPE|Floating point exception|Segmentation fault/ {
        print
        fflush()
        next
      }

      # Linhas úteis (amostradas por tempo de relógio)
      /^(Time =|Courant Number|ExecutionTime|forces|forceCoeffs|time step continuity errors)/ {
        now = systime()
        if (now - t >= s) {
          print
          fflush()
          t = now
        }
      }
    ' > "$LOG_KEY"

echo "Fim. Acompanhe com: tail -f $LOG_KEY"
