#!/bin/bash

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "ERROR: This script must be sourced:"
    echo "  source ./initialize.sh"
    exit 1
fi

export MANA_HOME=/home/andre_benevides/src/mana
export MPICH_HOME=/home/andre_benevides/opt/mpich/5.0.1
export PATH="$MPICH_HOME/bin:$MANA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$MPICH_HOME/lib:${LD_LIBRARY_PATH:-}"
export RUN_BASE="$HOME/mana-test-runs"

mkdir -p "$RUN_BASE"
cd "$MANA_HOME"

"$MPICH_HOME/bin/mpicc" -show
"$MPICH_HOME/bin/mpifort" -show
"$MPICH_HOME/bin/mpiexec" -info