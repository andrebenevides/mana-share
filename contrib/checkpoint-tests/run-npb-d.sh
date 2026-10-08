#!/usr/bin/env bash
# Run native and checkpoint/restart cases sequentially to limit memory demand.
set -euo pipefail
: "${NPB_ROOT:?Set NPB_ROOT to NPB3.4-MPI}"
: "${MPICH_HOME:?Set MPICH_HOME to the MPI installation used to build MANA}"
: "${RUN_BASE:?Set RUN_BASE to a directory with enough checkpoint storage}"
script_dir="$(cd "$(dirname "$0")" && pwd)"
options=(--class D --ranks "${RANKS:-16}" --work-base "$RUN_BASE"
         --checkpoint-timeout "${CHECKPOINT_TIMEOUT:-1800}"
         --run-timeout "${RUN_TIMEOUT:-14400}")
if [[ -n "${HOSTFILE:-}" ]]; then
    options+=(--hostfile "$HOSTFILE")
fi
for benchmark in bt cg; do
    for mode in native checkpoint; do
        python3 "$script_dir/run-test.py" "$benchmark" --mode "$mode" \
            --exe "$NPB_ROOT/bin/$benchmark.D.x" "${options[@]}"
    done
done
