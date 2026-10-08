# Documenting our group's pull requests

I want to install Mana in my Ubuntu to run checkpoint tests of parallel applications (mpi). One of my group members had a few issues with the default mana and implemented few changes that were submitted as 6 pull requests in github (but were not yet accepted).
I am not sure personally if those changes are needed for me, however I would add them if they make sense.

The PRs are listed in an umbrella issue here
[issues](https://github.com/mpickpt/mana/issues/485)

1. restart: resolve entries under --restartdir -#486
    - [restart](https://github.com/mpickpt/mana/pull/486)
    - [changes](https://github.com/mpickpt/mana/pull/486/changes)
2. coordinator: add persistent operation mode -#487
    - [coordinator](https://github.com/mpickpt/mana/pull/487)
    - [changes](https://github.com/mpickpt/mana/pull/487/changes)
3. lower-half: resolve loader debug file by build ID -#488
    - [lower-half](https://github.com/mpickpt/mana/pull/488)
    - [changes](https://github.com/mpickpt/mana/pull/488/changes)
4. test: add opt-in MPICH/Hydra multi-node checkpoint-restart -#489
    - [test](https://github.com/mpickpt/mana/pull/489)
    - [changes](https://github.com/mpickpt/mana/pull/489/changes)
5. docs: add distributed MPICH/Hydra workflow -#490
    - [docs](https://github.com/mpickpt/mana/pull/490)
    - [changes](https://github.com/mpickpt/mana/pull/490/changes)
6. Draft: expose required Hydra PMI_FD handling for MANA checkpoint/restart -#491
    - [Draft](https://github.com/mpickpt/mana/pull/491)
    - [changes](https://github.com/mpickpt/mana/pull/491/changes)

Here you will find the default cloned directory, ready to install mana. Can you go over the changes and implement the modifications please?

## Running a MANA checkpoint/restart test

The following commands use Bash and the patched checkout described in
[the integration notes](doc/local-pr-integration.md). Start with a small local
test before using a cluster or a large benchmark. The runnable examples are in
[`contrib/checkpoint-tests`](contrib/checkpoint-tests/).

### 1. Select the MPI installation and build MANA

On this machine, MPICH 5.0.1 is installed at the path below. Change these paths
on another machine; use the same MPICH for MANA and the applications.

```bash
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
```

This is included in initialize.sh.

```bash
source ./initialize.sh
```


Ubuntu needs a C/C++ compiler, GNU Fortran, Make, Python 3, binutils, and loader
debug symbols. If these are missing, install them before building:

```bash
sudo apt-get update
sudo apt-get install build-essential gfortran python3 binutils libc6-dbg curl
```

This package command supplies the toolchain; the examples use the separate
MPICH installation selected by `MPICH_HOME`. Keep `libc6-dbg` matched to the
installed libc. Build the patched source tree as follows:

```bash
git submodule update --init
bash contrib/dmtcp-patches/apply.sh
./configure CFLAGS='-O2 -fno-stack-protector' \
            CXXFLAGS='-O2 -fno-stack-protector'
make -j8 mana \
  MPICC="$MPICH_HOME/bin/mpicc" \
  MPICXX="$MPICH_HOME/bin/mpicxx -std=c++14" \
  MPIFORTRAN="$MPICH_HOME/bin/mpifort" \
  MPIRUN="$MPICH_HOME/bin/mpiexec" \
  MPI_LD_FLAG="-L$MPICH_HOME/lib -lmpi"

ldd "$MANA_HOME/bin/lower-half"
```

Confirm that `libmpi` resolves to the selected MPICH and that no library is
reported as missing. Pass the MPI overrides to subsequent `make` commands too.
The executables are built into `MANA_HOME/bin`; a system-wide install is not
required. Use paths without whitespace for these examples.

### 2. Run the fast regression checks

```bash
python3 ci/test-mana-restart.py -v
python3 ci/test-mana-coordinator.py -v
python3 ci/test-build-id-debug.py -v
python3 ci/multinode/test-verify.py -v
```

These 30 tests check the wrappers, loader-symbol lookup, and log verifier.
They do not perform a real MPI checkpoint. The existing MPI unit-test Makefile
has stale source dependencies, so use the following runtime test as well.

### 3. Run native MPI, then a real checkpoint/restart

The example runner compiles `ci/multinode/mpi_counter.c` with the chosen MPICH.
The native test runs five iterations; the checkpoint test uses an ongoing
counter and stops it after validating restart.

```bash
python3 contrib/checkpoint-tests/run-test.py counter \
  --mode native --ranks 2 --work-base "$RUN_BASE" --run-timeout 120

python3 contrib/checkpoint-tests/run-test.py counter \
  --mode checkpoint --ranks 2 --work-base "$RUN_BASE" \
  --checkpoint-timeout 120 --run-timeout 120
```

Each invocation prints a new evidence directory, for example
`$RUN_BASE/mana-counter-abcdefgh`. The checkpoint runner performs these steps:

1. Create isolated `home/`, `checkpoints/`, `tmp/`, and `logs/` directories.
   Its child processes use this temporary home for `.mana.rc`.
2. Start `mana_coordinator --persistent --port 0 --interval 0`. Port zero
   requests an available port; the runner reads the actual host and port from
   its status file and passes them to `dmtcp_command`.
3. Launch two ranks with MPICH's local `fork` launcher and `mana_launch`.
   Wait until the coordinator sees both ranks and the counter advances.
4. Request `dmtcp_command --bcheckpoint`, then wait for a non-empty `.dmtcp`
   image under every `checkpoints/ckpt_rank_N` and no remaining `.tmp` files.
   The bundled command can return before image creation finishes.
5. Let the application advance beyond the saved state, kill that computation
   through its coordinator, and wait for zero connected peers.
6. Start the same number of ranks with `mana_restart --restartdir ...`, from
   outside the checkpoint directory. Verify that every rank resumes from an
   earlier iteration, advances past its pre-stop progress, and produces the
   expected collective sum: `2 * ranks * iteration + ranks * (ranks - 1) / 2`.
7. Stop this run's MPI launcher and coordinator, retaining evidence for review.

Expect `PASS: counter native` and `PASS: counter checkpoint`, both with exit
status zero. Inspect the printed directory:

```bash
# Replace this example with the exact directory printed by the runner.
RUN="$RUN_BASE/mana-counter-abcdefgh"
cat "$RUN/result.json"
cat "$RUN/launch.log"
cat "$RUN/restart.log"
find "$RUN/checkpoints" -name '*.dmtcp' -type f -size +0c
find "$RUN/checkpoints" -name '*.tmp'
du -sh "$RUN/checkpoints"
```

`result.json` records pass/fail, ranks, executable, checkpoint time, and
original/restarted progress. A `.dmtcp` file alone does not establish success:
the resumed application must communicate and produce correct results.
Ctrl+C causes the runner to clean up its own processes and retain the logs.
Avoid broad process-killing commands on a shared machine.

### 4. Optional multi-node validation

Use two SSH-accessible machines with the same absolute MANA/MPICH paths and
compatible libraries. First confirm passwordless SSH and hostname resolution
between the nodes, including access to the coordinator host and port.

```bash
cat > "$RUN_BASE/hosts.txt" <<'EOF'
node01:1
node02:1
EOF
# Replace node01/node02 with the actual allocated machines.
ssh -n node01 hostname
ssh -n node02 hostname

export MANA_TEST_MPICH_HOME="$MPICH_HOME"
export MANA_TEST_HOSTFILE="$RUN_BASE/hosts.txt"
export MANA_TEST_WORKDIR=/tmp/mana-multinode-tests
export MANA_TEST_RANKS=2
export MANA_TEST_TIMEOUT=300
bash ci/multinode/run-mpich-hydra.sh
```

That runner supports shared storage or identical paths on separate local
storage and requires output from at least two distinct hosts. See
[its options](ci/multinode/README.md) and the
[distributed guide](doc/distributed-mpich-hydra.md) for node preparation.

## NAS Parallel Benchmarks: BT and CG Class D

These instructions use NASA's **NPB 3.4.4 MPI** implementation, with the
standard single-zone **BT (Block Tri-diagonal solver)** and **CG (Conjugate
Gradient)**. The download and version were checked against
[NASA's NPB page](https://www.nas.nasa.gov/software/npb.html).

### 1. Choose ranks, memory, and storage

| Benchmark | Standard Class D problem | Permitted rank counts | Example |
| --- | --- | --- | --- |
| BT | `408 × 408 × 408`, 250 iterations, time step `0.00002` | Perfect squares: 1, 4, 9, 16, … | 16 ranks |
| CG | 1,500,000 rows, `NONZER=21`, 100 iterations, shift 500 | Powers of two: 1, 2, 4, 8, 16, … | 16 ranks |

Problem parameters come from
[NASA's problem-size table](https://www.nas.nasa.gov/software/npb_problem_sizes.html);
rank restrictions are documented in `NPB3.4-MPI/README.install` in the
[source archive](https://www.nas.nasa.gov/assets/npb/NPB3.4.4.tar.gz).
NPB 3.4 chooses the process layout at runtime: build with `CLASS=D`, then
select ranks with `mpiexec -n`. Do not use the older `NPROCS=...` build recipe.
The runner enforces strict rank counts, so it cannot silently use fewer ranks.

Class D needs substantial memory. **Calculated from the main array allocations
in NPB 3.4.4**, at 16 ranks and conventional 8-byte doubles/4-byte integers,
BT allocates approximately **25.4 GiB aggregate** and CG **23.2 GiB aggregate**.
These estimates exclude MPI, MANA, allocator overhead, and other working
storage; they are not measured peak RSS. Source locations are `BT/bt_data.f90`
and `CG/cg_data.f90`. Memory per node depends on rank placement, and CG has
replicated arrays, so increasing ranks does not simply divide a fixed total.

Reserve additional RAM and checkpoint space before running Class D. A full
checkpoint can be comparable to the live process memory; keep room for all
ranks, temporary files, and retained runs. Compression is workload-dependent.
Use sufficiently large persistent scratch storage rather than a small `/tmp`
filesystem. Run BT and CG sequentially when sizing resources for one benchmark.

```bash
nproc
free -h
df -h "$RUN_BASE"
```

For multiple nodes, check these resources on each participating machine and
respect the CPU/memory allocation provided by your cluster scheduler.

### 2. Download the official source

Keep third-party sources and benchmark output outside the MANA source tree.
The following is a first-time setup; do not extract over a modified source tree.

```bash
export NPB_WORK="$HOME/npb-mana"
mkdir -p "$NPB_WORK"
cd "$NPB_WORK"
curl -fL --retry 3 \
  https://www.nas.nasa.gov/assets/npb/NPB3.4.4.tar.gz \
  -o NPB3.4.4.tar.gz
sha256sum NPB3.4.4.tar.gz | tee NPB3.4.4.sha256
tar -xzf NPB3.4.4.tar.gz
export NPB_ROOT="$NPB_WORK/NPB3.4.4/NPB3.4-MPI"
cd "$MANA_HOME"
```

The archive downloaded for this guide had SHA-256
`1ae219398e02a0a79ad51b7460fcffbf7b5df83a69d5d3d3a9dc2d8acf523549`.
This is a recorded local digest, not a separately published NASA signature.
The extracted directory name is `NPB3.4-MPI`, even though the release is 3.4.4.

### 3. Build BT and CG with the same MPICH as MANA

Use [`build-npb.sh`](contrib/checkpoint-tests/build-npb.sh):

```bash
# Small binaries for a quick native MPI check.
bash contrib/checkpoint-tests/build-npb.sh S

# A smaller checkpoint/restart trial before committing Class D resources.
bash contrib/checkpoint-tests/build-npb.sh B

# The requested Class D binaries. Compilation does not run the benchmarks.
bash contrib/checkpoint-tests/build-npb.sh D

ls -l "$NPB_ROOT/bin/bt.D.x" "$NPB_ROOT/bin/cg.D.x"
ldd "$NPB_ROOT/bin/bt.D.x"
ldd "$NPB_ROOT/bin/cg.D.x"
```

The script writes the selected compiler/linker settings into `config/make.def`,
saving an existing file once as `config/make.def.before-mana`. It cleans stale
objects/modules and runs these build targets sequentially:

```text
make bt CLASS=D F08=f
make cg CLASS=D F08=f
```

Writing the settings to `make.def` also makes NPB's printed compile-options
summary accurate; its metadata generator does not read command-line overrides.

`F08=f` selects `mpif.h`, matching MANA's existing legacy Fortran wrappers.
NASA also supports `F08=def` and `F08=f08`; this walkthrough does not claim
MANA compatibility with the `mpi_f08` interface. GNU Fortran uses
`-O2 -g -fallow-argument-mismatch` for the legacy MPI calls. Rank/type mismatch
warnings from these calls can still appear. Avoid `-ffast-math` and custom
problem parameters when checking standard NPB numerical verification.

The script leaves already-built `bin/*.x` executables in place, so the S, B,
and D binaries coexist. It does not modify the benchmark source code, use
`MPI_dummy`, select BT-IO, or add OpenMP. Build BT with an empty `SUBTYPE` to
run the solver; MANA supplies the process checkpoints independently of BT-IO.

### 4. Validate small cases first

Both benchmarks can use four ranks. Run the native Class S binaries first:

```bash
for bench in bt cg; do
  python3 contrib/checkpoint-tests/run-test.py "$bench" \
    --mode native --exe "$NPB_ROOT/bin/$bench.S.x" --class S \
    --ranks 4 --work-base "$RUN_BASE" --run-timeout 120
done
```

Then exercise MANA with Class B:

```bash
for bench in bt cg; do
  python3 contrib/checkpoint-tests/run-test.py "$bench" \
    --mode checkpoint --exe "$NPB_ROOT/bin/$bench.B.x" --class B \
    --ranks 4 --work-base "$RUN_BASE" \
    --checkpoint-timeout 300 --run-timeout 1800
done
```

An extremely short run may finish before a checkpoint is possible. That is a
failed checkpoint test, even if native NPB verification succeeded. Use a larger
class or fewer valid ranks; do not change the standard iteration count merely
to keep a Class S run alive. The runner requests a checkpoint as soon as the
initial progress output appears; `--checkpoint-delay SECONDS` optionally waits
longer after that point. It sets `GFORTRAN_UNBUFFERED_ALL=y` so progress can be
observed when output is redirected to files.

### 5. Run the Class D baseline and checkpoint/restart tests

After allocating sufficient resources, run the provided batch script:

```bash
# Select a persistent filesystem with enough free space.
export RUN_BASE="$HOME/npb-mana-runs"
mkdir -p "$RUN_BASE"
export RANKS=16
export CHECKPOINT_TIMEOUT=1800
export RUN_TIMEOUT=14400
unset HOSTFILE  # Single-machine run; optional cluster setup is below.
bash contrib/checkpoint-tests/run-npb-d.sh
```

[`run-npb-d.sh`](contrib/checkpoint-tests/run-npb-d.sh) runs BT native, BT
checkpoint/restart, CG native, and CG checkpoint/restart, sequentially. It
stops on the first failure. The timeout values are examples in seconds, not
predicted running times; increase them for your machine and filesystem.

To run just one case, use the underlying command:

```bash
python3 contrib/checkpoint-tests/run-test.py bt \
  --mode checkpoint --exe "$NPB_ROOT/bin/bt.D.x" --class D \
  --ranks 16 --work-base "$RUN_BASE" \
  --checkpoint-timeout 1800 --run-timeout 14400

python3 contrib/checkpoint-tests/run-test.py cg \
  --mode checkpoint --exe "$NPB_ROOT/bin/cg.D.x" --class D \
  --ranks 16 --work-base "$RUN_BASE" \
  --checkpoint-timeout 1800 --run-timeout 14400
```

Use `--mode native` with the same executable and ranks for a corresponding
baseline. Each run starts in a fresh directory without `inputbt.data`, so BT
uses the compiled standard Class D parameters.

The NPB runner follows the counter test's coordinator/checkpoint/kill/restart
sequence. After saving the images it waits for more progress output (or normal
completion) before stopping the original run, then restarts the saved state.
It retains the same binary, MPI installation, rank count, working-directory
paths, and checkpoint layout throughout. Do not rebuild or move the executable
between checkpoint and restart.

For a pass, the restarted benchmark must finish with exit status zero and
report all of the following in `restart.log`:

```text
Class           = D
Total processes = 16
Active processes= 16
Verification    = SUCCESSFUL
```

The runner checks those fields and requires the first resumed progress value
to be below the final original progress, followed by recovery of that progress.
BT prints `Time step`; CG prints iteration/residual/zeta rows. NPB's built-in
verification checks the final numerical result. NPB progress is printed by
the root rank, so this is not an independent per-rank arithmetic trace like
the counter test. Keep both tests in the validation procedure.

Review `native.log`, `launch.log`, `restart.log`, `result.json`, and the image
directory for each run. The timed NPB section can span checkpoint and downtime
after a restart, so its Mop/s and elapsed-time fields should not be treated as
a clean performance baseline. The runner's `checkpoint_seconds` measures the
request through observed image completion, including polling overhead.

### 6. Adapt the NPB scripts to multiple nodes

The basic NPB runner's `--hostfile` option assumes **shared storage**: all nodes
must see the same absolute `RUN_BASE`, NPB executable, MANA, and MPICH paths.
It uses Hydra's SSH launcher with an explicit working directory. For example,
after preparing a shared mount and allocating two nodes:

```bash
export RUN_BASE=/shared/scratch/your-user/mana-npb
mkdir -p "$RUN_BASE"
export HOSTFILE="$RUN_BASE/hosts.txt"
cat > "$HOSTFILE" <<'EOF'
node01:8
node02:8
EOF
export RANKS=16
bash contrib/checkpoint-tests/run-npb-d.sh
```

Replace node names and paths with your actual allocation. Confirm noninteractive
SSH first, and use a coordinator hostname that all ranks can resolve and reach.
Keep the same hostfile and rank placement for launch and restart. These examples
use the same SSH account on each node. Scheduler-managed systems may require
a site-specific launcher; these scripts explicitly use Hydra/SSH.

For node-local checkpoint storage, use the existing multi-node counter test
first and adapt its directory creation/status-file propagation logic before
using the NPB runner. Passing a hostfile alone does not copy binaries, status
files, or checkpoint images to remote machines.

### Validation status and troubleshooting

The scripts were checked with Ubuntu 22.04.5, MPICH 5.0.1, and the official
NPB 3.4.4 source. Class S, B, and D BT/CG binaries were built. The counter
checkpoint/restart test passed; both Class S native runs and both Class B
checkpoint/restart runs passed, including NPB numerical verification and
observed rollback. Class D execution and multi-node NPB execution still require
validation with the intended resources; building Class D alone does not
validate its checkpoint/restart.

- **No coordinator / no peers:** Read this run's `coordinator.log`, verify its
  `.mana.rc` host/port, and confirm consistent MPI paths and remote connectivity.
- **Missing loader symbols:** Check the installed `libc6-dbg` version or set
  `MANA_DEBUG_ROOT` to matching detached symbols before launching the runner.
- **Killed process / allocation failure:** Check per-node RAM and scheduler
  memory limits; begin with Class B before allocating resources for Class D.
- **Checkpoint timeout / `.tmp` remains:** Inspect logs and available storage.
  Keep the partial run for diagnosis and start a fresh run after resolving the
  cause. The runner rejects incomplete images.
- **Incorrect class, inactive ranks, or failed verification:** Check the NPB
  executable, rank restrictions, compiler/MPI consistency, and native baseline.
  A successful MPI exit alone does not establish numerical correctness.
- **Rewind not demonstrated:** Checkpoint earlier or choose a longer run; sparse
  progress output can otherwise leave insufficient evidence of rollback.

Source references: [NASA NPB overview/downloads](https://www.nas.nasa.gov/software/npb.html),
[problem parameters](https://www.nas.nasa.gov/software/npb_problem_sizes.html),
[release changes](https://www.nas.nasa.gov/software/npb_changes.html), and
`README.install`, `BT/bt_data.f90`, and `CG/cg_data.f90` in the downloaded archive.
