# Opt-in MPICH/Hydra multi-node test

This test is not run unless `MANA_TEST_HOSTFILE` is set.

## Required variables

- `MANA_HOME`: configured and built MANA source/install tree available at the same absolute path on every node.
- `MANA_TEST_MPICH_HOME`: MPICH installation available at the same absolute path on every node.
- `MANA_TEST_HOSTFILE`: Hydra hostfile or a plain file containing one host per line.

## Optional variables

- `MANA_TEST_REMOTE_USER` (default: current user)
- `MANA_TEST_RANKS` (default: 2)
- `MANA_TEST_COORD_PORT` (default: 7780)
- `MANA_TEST_WORKDIR` (default: `/tmp`): parent directory for a fresh,
  uniquely named `mana-multinode.XXXXXXXX` directory on every node.
- `MANA_TEST_TIMEOUT` (default: 300 seconds)
- `MANA_TEST_SSH` (default: `ssh`)
- `MANA_TEST_SCP` (default: `scp`)

## What it validates

1. Remote connectivity and identical executable paths.
2. Native MPICH/Hydra execution.
3. Finite MANA launch.
4. Persistent DMTCP coordinator behavior.
5. Long-running distributed MANA launch.
6. Blocking checkpoint with timeout.
7. Non-empty images and absence of `.tmp` files.
8. Kill and restart.
9. Rollback and post-restart `MPI_Allreduce` correctness.

The script requires at least two hosts and two ranks. MANA, MPICH, and work
paths must be absolute and contain only letters, digits, `_`, `.`, `/`, or `-`.
It supports shared storage and separate local storage with the same paths;
rank placement must stay the same across launch and restart for local images.

Each run creates its own directory below `MANA_TEST_WORKDIR`. Cleanup sends
commands only to that run's coordinator and stops the launchers it started;
Hydra cleans up their remote processes. Logs and images remain in the printed
evidence directory. No process-name matching is used.

The verifier requires output from every rank on at least two distinct hosts,
a strictly earlier iteration after restart for each rank, correct collective
results, and progress beyond the last original iteration. Run its local tests
with `python3 ci/multinode/test-verify.py -v`.
