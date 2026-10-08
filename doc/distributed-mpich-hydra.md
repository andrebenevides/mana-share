# Distributed MPICH/Hydra checkpoint and restart

This guide describes an opt-in, multi-node MANA workflow using MPICH's
Hydra process manager and SSH launch.

Paths and node names below are examples. Unless a directory is stored on
shared storage, every participating node must use the same absolute paths for:

- MANA;
- MPICH;
- the MPI application;
- the working directory;
- temporary files;
- checkpoint files;
- the isolated test home containing `.mana.rc`.

## 1. Prerequisites

Each node needs:

- the same MANA revision and build;
- the same MPICH installation;
- passwordless SSH from the launch node;
- a working C and C++ compiler toolchain;
- compatible runtime libraries;
- write access to the selected working, checkpoint, temporary, and log
  directories;
- loader debug symbols when required by the lower half.

The launch node also needs a Hydra hostfile containing one host or host
specification per line.

Do not store private SSH keys, scheduler credentials, checkpoint images,
status files, or cluster-specific hostfiles in the MANA repository.

## 2. Build MANA against the intended MPICH

Do not rely on whichever `mpicc` happens to be first in the system path.
An accidental Open MPI build can instantiate incompatible `ompi_*` handle
types.

```bash
export MPICH_HOME=/opt/mpich-mana

export PATH="$MPICH_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$MPICH_HOME/lib:${LD_LIBRARY_PATH:-}"

# Apply the recorded bundled-DMTCP fix before building (safe to repeat).
bash contrib/dmtcp-patches/apply.sh

./configure CFLAGS="-O2 -fno-stack-protector" \
            CXXFLAGS="-O2 -fno-stack-protector"

make -j8 mana \
  MPICC="$MPICH_HOME/bin/mpicc" \
  MPICXX="$MPICH_HOME/bin/mpicxx -std=c++14" \
  MPIFORTRAN="$MPICH_HOME/bin/mpifort" \
  MPIRUN="$MPICH_HOME/bin/mpiexec" \
  MPI_LD_FLAG="-L$MPICH_HOME/lib -lmpi"
```

This revision defines MPI tools in `mpi-proxy-split/Makefile_config.in`;
passing `MPICC` and related variables only in `./configure`'s environment
does not override those definitions. Pass them to `make` as shown, including
on subsequent builds. Adjust `lib` to `lib64` when required by your MPICH
installation. Use `make mana` to build the binaries into the source tree's
`bin` directory; a system-wide install is not required.

Check the lower-half linkage:

```bash
ldd bin/lower-half |
grep -E 'libmpi|not found'
```

The MPI library should resolve under `$MPICH_HOME/lib`, and no library should
be reported as `not found`.

The file below is a generated executable and must not be committed:

```text
mpi-proxy-split/lower-half/lower-half
```

## 3. Define the distributed test environment

For example:

```bash
export MANA_HOME=/opt/mana
export MPICH_HOME=/opt/mpich-mana

export HOSTFILE=/path/to/hosts.txt
export REMOTE_USER="$USER"

export WORKDIR=/tmp/mana-distributed-test
export TEST_HOME="$WORKDIR/home"
export CKPTDIR="$WORKDIR/checkpoints"
export TMPDIR="$WORKDIR/tmp"
export LOGDIR="$WORKDIR/logs"

export STATUS_FILE="$TEST_HOME/.mana.rc"
```

`TEST_HOME` is intentionally separate from the user's normal home directory.
MANA launch and restart commands read coordinator information from:

```text
$HOME/.mana.rc
```

The MPI ranks will therefore receive:

```bash
-genv HOME "$TEST_HOME"
```

The same absolute `TEST_HOME` path must exist on every node.

## 4. Validate SSH, paths, and runtime libraries

For every unique host:

```bash
while IFS= read -r node || [[ -n "$node" ]]; do
    node="${node%%[[:space:]]*}"

    [[ -z "$node" || "$node" == \#* ]] && continue

    ssh -n "$REMOTE_USER@$node" "
      set -e

      test -x '$MANA_HOME/bin/mana_launch'
      test -x '$MANA_HOME/bin/mana_restart'
      test -x '$MANA_HOME/bin/lower-half'
      test -x '$MPICH_HOME/bin/hydra_pmi_proxy'

      mkdir -p \
        '$WORKDIR' \
        '$TEST_HOME' \
        '$CKPTDIR' \
        '$TMPDIR' \
        '$LOGDIR'
    "
done < "$HOSTFILE"
```

Use `ssh -n` in loops that read standard input. Without `-n`, SSH can consume
the remaining hostfile lines.

Check unresolved libraries on each node:

```bash
while IFS= read -r node || [[ -n "$node" ]]; do
    node="${node%%[[:space:]]*}"

    [[ -z "$node" || "$node" == \#* ]] && continue

    echo "===== $node ====="

    ssh -n "$REMOTE_USER@$node" "
      export LD_LIBRARY_PATH='$MANA_HOME/lib:$MANA_HOME/lib/dmtcp:$MPICH_HOME/lib'

      unresolved=\$(
        ldd '$MANA_HOME/bin/lower-half' |
        grep 'not found' || true
      )

      if [[ -n \"\$unresolved\" ]]; then
        printf '%s\n' \"\$unresolved\"
        exit 1
      fi

      ldd '$MANA_HOME/bin/lower-half' |
      grep -E 'libmpi|libatomic' || true
    "
done < "$HOSTFILE"
```

A copied binary can fail remotely when a runtime package exists only on the
build node. Resolve all missing libraries before testing MANA.

## 5. Run a native MPICH/Hydra smoke test

Hydra normally propagates the launch node's current directory. Supply `-wdir`
explicitly so remote ranks do not inherit a directory that exists only on the
launch node.

```bash
"$MPICH_HOME/bin/mpiexec" \
  -launcher ssh \
  -launcher-exec /usr/bin/ssh \
  -wdir "$WORKDIR" \
  -f "$HOSTFILE" \
  -n 2 \
  /absolute/path/to/mpi_application
```

Confirm that every expected host and rank appears before involving MANA.

The native application should execute at least one MPI collective and terminate
normally.

## 6. Start the coordinator

For an externally launched Hydra job, the coordinator can briefly have zero
clients before the MPI ranks connect.

Use the integrated `--persistent` option so the coordinator remains available
across zero-client intervals. The default still exits after the last client:

```bash
mkdir -p \
  "$WORKDIR" \
  "$TEST_HOME" \
  "$CKPTDIR" \
  "$TMPDIR" \
  "$LOGDIR"

COORD_LOG="$LOGDIR/coordinator.log"

env -u SLURM_JOB_ID HOME="$TEST_HOME" \
  "$MANA_HOME/bin/mana_coordinator" --persistent \
  --port 7780 \
  --interval 0 \
  --ckptdir "$CKPTDIR" \
  --coord-logfile "$COORD_LOG"
```

Inspect the generated status file:

```bash
cat "$STATUS_FILE"
```

Copy it to the same absolute path on every node when the path is not shared:

```bash
while IFS= read -r node || [[ -n "$node" ]]; do
    node="${node%%[[:space:]]*}"

    [[ -z "$node" || "$node" == \#* ]] && continue

    ssh -n "$REMOTE_USER@$node" \
      "mkdir -p '$TEST_HOME'"

    scp -q \
      "$STATUS_FILE" \
      "$REMOTE_USER@$node:$STATUS_FILE" \
      </dev/null
done < "$HOSTFILE"
```

The wrapper writes `$TEST_HOME/.mana.rc`. The opt-in regression harness starts
`dmtcp_coordinator` directly without `--exit-on-last` to choose its status file.
For this SSH workflow, unset inherited `SLURM_JOB_ID` and `SLURM_JOBID` before
launching MPI so the wrappers use `.mana.rc` rather than a Slurm-specific file.

## 7. Run a finite MANA smoke test

```bash
"$MPICH_HOME/bin/mpiexec" \
  -launcher ssh \
  -launcher-exec /usr/bin/ssh \
  -wdir "$WORKDIR" \
  -f "$HOSTFILE" \
  -n 2 \
  -genv HOME "$TEST_HOME" \
  -genv MANA_HOME "$MANA_HOME" \
  -genv MPICH_HOME "$MPICH_HOME" \
  -genv PATH "$MANA_HOME/bin:$MPICH_HOME/bin:$PATH" \
  -genv LD_LIBRARY_PATH "$MANA_HOME/lib:$MANA_HOME/lib/dmtcp:$MPICH_HOME/lib:${LD_LIBRARY_PATH:-}" \
  "$MANA_HOME/bin/mana_launch" \
  --ckptdir "$CKPTDIR" \
  --tmpdir "$TMPDIR" \
  /absolute/path/to/finite_mpi_application
```

The finite application should:

- execute at least one MPI collective;
- print all expected ranks;
- terminate normally.

Using `TEST_HOME` prevents the test from reading or overwriting the user's
normal `~/.mana.rc`.

## 8. Launch a long-running MANA application

Launch the longer application with the same Hydra and MANA environment:

```bash
"$MPICH_HOME/bin/mpiexec" \
  -launcher ssh \
  -launcher-exec /usr/bin/ssh \
  -wdir "$WORKDIR" \
  -f "$HOSTFILE" \
  -n 2 \
  -genv HOME "$TEST_HOME" \
  -genv MANA_HOME "$MANA_HOME" \
  -genv MPICH_HOME "$MPICH_HOME" \
  -genv PATH "$MANA_HOME/bin:$MPICH_HOME/bin:$PATH" \
  -genv LD_LIBRARY_PATH "$MANA_HOME/lib:$MANA_HOME/lib/dmtcp:$MPICH_HOME/lib:${LD_LIBRARY_PATH:-}" \
  "$MANA_HOME/bin/mana_launch" \
  --ckptdir "$CKPTDIR" \
  --tmpdir "$TMPDIR" \
  /absolute/path/to/long_running_mpi_application
```

Save original-execution output separately from restart output so rollback can
be measured accurately.

Before requesting a checkpoint, wait until:

```bash
"$MANA_HOME/bin/dmtcp_command" \
  --coord-host "$(
    awk '/^Host:/ {print $2; exit}' "$STATUS_FILE"
  )" \
  --coord-port "$(
    awk '/^Port:/ {print $2; exit}' "$STATUS_FILE"
  )" \
  --status
```

reports the expected number of peers.

## 9. Request a blocking checkpoint

Always apply a timeout:

```bash
coord_host="$(
  awk '/^Host:/ {print $2; exit}' "$STATUS_FILE"
)"

coord_port="$(
  awk '/^Port:/ {print $2; exit}' "$STATUS_FILE"
)"

timeout \
  --signal=TERM \
  --kill-after=20s \
  300s \
  "$MANA_HOME/bin/dmtcp_command" \
  --coord-host "$coord_host" \
  --coord-port "$coord_port" \
  --bcheckpoint
```

A successful command return code is not sufficient. Verify:

- at least one non-empty `.dmtcp` image per rank;
- no `.tmp` files remain;
- the coordinator returns to a running state;
- application output continues after checkpoint creation.

For example:

```bash
find "$CKPTDIR" \
  -type f \
  -name '*.dmtcp' \
  -size +0c \
  -print
```

Reject incomplete checkpoint attempts:

```bash
find "$CKPTDIR" \
  -type f \
  -name '*.tmp' \
  -print
```

The final command should produce no output.

## 10. Stop and restart

Stop only the test-owned MPI execution while preserving the checkpoint images.

Start a fresh persistent coordinator and redistribute its status file to:

```text
$TEST_HOME/.mana.rc
```

The integrated `mana_restart` resolves `--restartdir` to an absolute path,
checks entries beneath that directory, and puts the rank image after other
DMTCP options. It can restart from an unrelated working directory:

```bash
"$MPICH_HOME/bin/mpiexec" \
  -launcher ssh \
  -launcher-exec /usr/bin/ssh \
  -wdir "$WORKDIR" \
  -f "$HOSTFILE" \
  -n 2 \
  -genv HOME "$TEST_HOME" \
  -genv MANA_HOME "$MANA_HOME" \
  -genv MPICH_HOME "$MPICH_HOME" \
  -genv PATH "$MANA_HOME/bin:$MPICH_HOME/bin:$PATH" \
  -genv LD_LIBRARY_PATH "$MANA_HOME/lib:$MANA_HOME/lib/dmtcp:$MPICH_HOME/lib:${LD_LIBRARY_PATH:-}" \
  -genv DMTCP_LOG_LEVEL trace \
  "$MANA_HOME/bin/mana_restart" \
  --verbose \
  --ckptdir "$CKPTDIR" \
  --tmpdir "$TMPDIR" \
  --restartdir "$CKPTDIR"
```

## 11. Verify correctness after restart

A useful validation application prints, for every iteration:

```text
rank
communicator size
hostname
PID
iteration
collective result
```

Verify all of the following:

1. After creating the checkpoint, let every rank advance for several more
   iterations before stopping it. Each rank must resume at a strictly earlier
   iteration than its final pre-stop iteration.
2. Post-restart iteration numbers continue increasing.
3. Every expected rank reconnects.
4. Collective results match the mathematically expected value.
5. The application continues making forward progress.
6. A second checkpoint can be created after restart when chained
   checkpoint/restart is under test.

## 12. Loader debug symbols

On distributions that install detached loader symbols under GNU build-ID paths,
identify the loader and its debug file with:

```bash
loader=/lib64/ld-linux-x86-64.so.2
real_loader="$(readlink -f "$loader")"

build_id="$(
  readelf -n "$real_loader" |
  awk '/Build ID:/ {print $3; exit}'
)"

debug_file="/usr/lib/debug/.build-id/${build_id:0:2}/${build_id:2}.debug"

printf 'Loader: %s\n' "$real_loader"
printf 'Debug:  %s\n' "$debug_file"

test -f "$debug_file"
```

Check the required symbols:

```bash
readelf -sW "$debug_file" |
awk '$NF == "mmap" || $NF == "munmap"'
```

The integrated lower half looks up this standard build-ID location directly.
Install Ubuntu's `libc6-dbg` package matching the installed libc if it is missing.
Set `MANA_DEBUG_ROOT` to a custom debug root when needed; MANA searches
`$MANA_DEBUG_ROOT/.build-id/xx/yyyy.debug`. Propagate it to all MPI ranks.
No compatibility symlink under `/usr/lib/debug` is required.

## 13. MPICH/Hydra PMI descriptor handling

In the validated MPICH/Hydra environment, complete checkpoint and restart also
required DMTCP socket handling to recognize `PMI_FD` alongside the existing
Hydra descriptor condition.

This dependency changes code inside MANA's DMTCP submodule and should therefore
be reviewed separately from unrelated MANA changes.

The exact delta and idempotent helper are in
[`contrib/dmtcp-patches`](../contrib/dmtcp-patches/README.md). This checkout
uses that local patch without changing the upstream submodule commit.
Reapply it before building after resetting or replacing the submodule.

When diagnosing an environment where native MPI and MANA launch succeed but
checkpoint or restart does not complete, record:

```bash
env |
grep -E '^(HYDI_CONTROL_FD|PMI_FD)=' || true
```

Locate the existing DMTCP Hydra handling:

```bash
git -C "$MANA_HOME/dmtcp" grep -n -C 5 \
  'HYDI_CONTROL_FD' \
  -- '*socketconnlist.cpp'
```

The validated condition included both:

```cpp
(getenv("HYDI_CONTROL_FD")) ||
(getenv("PMI_FD"))
```

The final ownership of this correction may be:

- a DMTCP upstream change;
- a temporary MANA-maintained compatibility patch;
- an equivalent MANA-side solution;
- another approach preferred by the maintainers.

## 14. Safe cleanup

Avoid broad commands such as:

```text
pkill -9 -f mana
killall dmtcp_coordinator
```

on shared systems.

Record launcher PIDs and stop only those launchers and their coordinator.
The regression harness uses a fresh directory for each run and lets Hydra
clean up its remote proxies.

Stop the coordinator through `dmtcp_command` when possible:

```bash
"$MANA_HOME/bin/dmtcp_command" \
  --coord-host "$coord_host" \
  --coord-port "$coord_port" \
  --quit
```

Keep logs, status files, hostfiles, checkpoint images, and generated binaries
outside the Git working tree.

## 15. Opt-in regression test

Run the included test after building the patched stack:

```bash
export MANA_HOME=/path/to/built/mana
export MANA_TEST_MPICH_HOME=/path/to/mpich
export MANA_TEST_HOSTFILE=/path/to/hosts.txt
export MANA_TEST_WORKDIR=/absolute/parent/path/on/all/nodes
export MANA_TEST_REMOTE_USER="$USER"

bash ci/multinode/run-mpich-hydra.sh
```

The test skips successfully when `MANA_TEST_HOSTFILE` is unset.

The test creates a unique subdirectory below `MANA_TEST_WORKDIR`, prints its
path, and retains logs and checkpoint images there. It requires at least two
hosts and two ranks; use absolute paths without spaces or shell metacharacters.
The manual SSH loops above assume plain one-host-per-line files; the automated
runner also parses Hydra `host:slots` entries. It verifies distinct hosts,
all ranks, strict rewind, progress, and collective results.

For the review decisions, exact PR revisions, and validation performed in this
checkout, see [the local integration notes](local-pr-integration.md).
