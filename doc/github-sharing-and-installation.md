# Sharing this MANA version and installing it on another machine

## What is actually in this folder?

Inspected on 2026-10-08, before adding this guide: the Windows folder
`checkpoint/src/mana` contained **27 files totaling 185,419 bytes (181 KiB)**.
Its largest file was `mpi-proxy-split/lower-half/lower-half.cpp`, at 54,797
bytes. There were **no compiled binaries, object files, shared libraries,
checkpoint images, or large generated files** anywhere in this folder,
including hidden files.

This folder is a **partial copy of modifications**, not an installable MANA
checkout. It has no `configure`, top-level build templates, `.gitmodules`,
complete MPI wrappers, or complete DMTCP source. Uploading only its current
contents would not give your friend a buildable installation.

The local integration notes identify the intended starting revisions:

```text
MANA:  f296e33267598d12bc0886f67774e20dda58c77e
DMTCP: ff8e28969def414dcc5e51ae611412ca389b759f
```

These hashes come from `doc/local-pr-integration.md`; they were not independently
verified against a complete checkout during this audit. The Linux directories
named in `initialize.sh`, `/home/andre_benevides/src/mana` and
`/home/andre_benevides/opt/mpich/5.0.1`, do not exist in this machine's Ubuntu
WSL instance. Recover the missing files from the machine where that build was
performed, or from another backup of the **final locally modified version**.
Applying the original PRs alone does not reproduce the additional fixes in
`changelog_personal.md`.

## Which files should go on GitHub?

Use a dedicated MANA fork or repository containing the **complete upstream
MANA source plus your modifications**, with MANA at its root. Your friend
should find `configure`, `README.md`, `ci/`, and `mpi-proxy-split/` directly
after entering the cloned repository. Keep upstream license/copyright files,
build scripts, source, headers, build templates, and documentation. Do not
publish the unrelated parent `checkpoint` project just to share MANA.

Keep DMTCP as the upstream **Git submodule**: commit `.gitmodules` and the
submodule's pinned commit reference. Your friend downloads its full source
with `git submodule update --init --recursive`. DMTCP does not need to be
copied into your repository as thousands of ordinary files.

### Modified/new source checklist

Paths below are relative to the MANA repository root. This is the checklist
for your changes; the unmodified upstream source is also required.

| Files | Status in this Windows copy | Purpose |
| --- | --- | --- |
| `bin/mana_restart` | **Missing; recover** | Restart-directory fixes, argument handling, startup race fixes |
| `bin/mana_coordinator` | **Missing; recover** | Persistent coordinator, argument handling, startup checks |
| `bin/mana_launch` | **Missing; recover** | Coordinator status-file startup race fix |
| `mpi-proxy-split/lower-half/Makefile` | **Missing; recover** | Build/link the new build-ID resolver |
| `mpi-proxy-split/lower-half/build-id-debug.cpp`, `build-id-debug.h`, `lower-half.cpp`, `get-symbol-offset.c` | Present | Loader/debug-symbol resolution |
| `ci/test-mana-restart.py`, `ci/test-mana-coordinator.py`, `ci/test-build-id-debug.py`, `ci/unit-test.sh` | Present | Regression tests and combined CI checks |
| `ci/multinode/mpi_counter.c`, `run-mpich-hydra.sh`, `README.md`, `verify.py`, `test-verify.py` | Present | Multi-node workload, runner, and verification |
| `doc/distributed-mpich-hydra.md`, `doc/local-pr-integration.md`, `README.md`, `changelog_personal.md` | Present | Usage, integration decisions, and recorded validation |
| `contrib/dmtcp-patches/0001-ipc-skip-socket-scan-when-PMI_FD-is-set.patch` | **Missing; recover or regenerate** | Reproducible DMTCP modification |
| `contrib/dmtcp-patches/apply.sh`, `README.md` | Present | Apply/document that patch |
| `contrib/checkpoint-tests/build-npb.sh`, `run-npb-d.sh`, `run-test.py` | Present | Additional counter/NPB test helpers |
| `.gitignore`, `doc/github-sharing-and-installation.md` | Present | Sharing exclusions and this guide |
| `desc.md` | Present; optional | Longer local walkthrough and original task context |

There is also a modified copy of
`dmtcp/src/plugin/ipc/socket/socketconnlist.cpp`. In a submodule-based release,
publish its **patch in the parent MANA repository**, then apply it after
initializing DMTCP. A MANA commit does not include uncommitted changes inside
the DMTCP submodule. Do not rely on copying that one C++ file into an otherwise
empty `dmtcp/` directory.

`initialize.sh` and `update.sh` are personal helpers, not installation
prerequisites. Their paths refer to your original Linux home. Either leave
them out of the release or adapt them and document their use. The current
`update.sh` also omits all three modified `bin/mana_*` scripts and the patch
file, so it cannot export the full modified version.

### Assembling a complete release checkout

On Linux, start from the complete modified checkout if you still have it.
Alternatively, make a separate checkout of the recorded upstream revision:

```bash
git clone https://github.com/mpickpt/mana.git mana-share
cd mana-share
git switch -c personal-mpich-hydra f296e33267598d12bc0886f67774e20dda58c77e
git submodule update --init --recursive
git -C dmtcp rev-parse HEAD
```

The last command should show the DMTCP revision recorded above. If either
revision cannot be fetched or differs, resolve that discrepancy before
publishing; do not silently substitute the latest upstream code. Overlay the
files in the checklist from your recovered modified copy, retaining relative
paths. Copy only the curated source changes; keep the newly initialized
DMTCP checkout and apply your patch to it.

If the patch file is lost, regenerate it from the original complete DMTCP
checkout **after reviewing its diff and confirming the only intended change
is the added `PMI_FD` condition**:

```bash
# Run inside the complete, locally modified MANA checkout.
git -C dmtcp diff -- src/plugin/ipc/socket/socketconnlist.cpp
git -C dmtcp diff -- src/plugin/ipc/socket/socketconnlist.cpp \
  > contrib/dmtcp-patches/0001-ipc-skip-socket-scan-when-PMI_FD-is-set.patch
test -s contrib/dmtcp-patches/0001-ipc-skip-socket-scan-when-PMI_FD-is-set.patch
```

This assumes the DMTCP `HEAD` is still the recorded upstream commit. If only
the copied C++ file survives, compare it to that file in a fresh checkout of
the recorded DMTCP revision and generate the equivalent Git diff there.
The existing `apply.sh` expects exactly the patch filename above.

Preserve Unix LF line endings and executable permissions, especially when
copying through Windows. The three `bin/mana_*` files are text source scripts
despite having no extension. The lower-half `Makefile` is also source.
The local `.gitignore` now makes narrow exceptions for these four files;
compiled binaries in `bin/` remain ignored.

From the complete release checkout, stage the changes explicitly:

```bash
git add -u
git add .gitignore README.md changelog_personal.md ci doc \
  contrib/dmtcp-patches contrib/checkpoint-tests \
  mpi-proxy-split/lower-half/build-id-debug.cpp \
  mpi-proxy-split/lower-half/build-id-debug.h
git add -f bin/mana_coordinator bin/mana_launch bin/mana_restart \
  mpi-proxy-split/lower-half/Makefile
git update-index --chmod=+x bin/mana_coordinator bin/mana_launch bin/mana_restart
git diff --cached --stat
git diff --cached --check
git status --short
```

Review everything staged before committing. `git add -u` captures changes to
already tracked upstream files, even if an ignore pattern matches them;
ignore rules do not remove files already tracked by Git. Verify that the patch
is staged and the DMTCP commit reference remains the intended upstream commit.
A dirty DMTCP submodule after applying the patch is expected. Run the build
and checks below in this release checkout before committing and pushing the
branch to your GitHub fork. Share the fork URL and branch name with your friend.

## Which generated files should be excluded?

The inspected Windows copy contains none of these. In a complete checkout
that has been built or used for experiments, exclude the following:

| Generated content | Examples |
| --- | --- |
| Compiled objects/libraries | `*.o`, `*.a`, `*.so`, versioned `*.so.*` |
| Compiled executables | `bin/lower-half`, `mpi-proxy-split/lower-half/lower-half`, generated `bin/dmtcp_*`, compiled test executables |
| Build/install directories | Generated content in `lib/`, `local/`, `build/`, plus dependency caches such as `.deps/` |
| Configure output | `config.log`, `config.status`, generated config headers, generated Makefiles and `mpi-proxy-split/Makefile_config` |
| Checkpoint/runtime output | `ckpt_rank_*/`, `*.dmtcp`, partial checkpoint `.tmp` files, generated restart scripts, `.mana.rc`, run directories and logs |
| Benchmark/dependency builds | NPB binaries, MPICH installation/build trees, downloaded source archives |

Checkpoint images can be particularly large because they contain application
memory. Keep `RUN_BASE` outside the repository as in the examples below.
Do not upload your installed MPICH, compiled DMTCP, or `.git/` directory.

**Do not exclude every file in `bin/` or every `Makefile` from a source
release.** Keep all upstream-tracked source scripts and hand-maintained build
rules, alongside `Makefile.in`, `Makefile.am`, `configure`, `configure.ac`,
headers, and license files. A file being executable does not make it a
compiled binary. The existing ignore file is useful but does not cover every
possible experimental output; review staged files before pushing.

Useful read-only checks from a Linux release checkout:

```bash
git status --short --ignored
git ls-files bin mpi-proxy-split/lower-half
find . -path './.git' -prune -o -type f -size +20M -print
du -sh bin lib dmtcp 2>/dev/null
```

The 20 MiB threshold is just an audit aid, not a rule that smaller generated
files belong on GitHub. No cleanup/deletion is necessary in the current
Windows copy.

## Installation instructions for your friend

These steps assume you have first published the **complete recovered source
tree** described above. They cannot build the current partial Windows copy.
Use Bash on Linux; Ubuntu 22.04 x86-64 is the environment recorded in the
integration notes. If using WSL, build in the Linux home filesystem with paths
without spaces. Native Windows compilation is not covered by this guide.

### 1. Install the build tools and loader debug symbols

```bash
sudo apt-get update
sudo apt-get install git build-essential gfortran python3 binutils \
  libc6-dbg curl ca-certificates autoconf automake libtool
```

`libc6-dbg` must match the installed glibc. This version's lower-half loader
uses internal dynamic-loader symbols. The added resolver can locate detached
debug files by GNU build ID; `MANA_DEBUG_ROOT` can point to an alternate debug
symbol root when matching symbols are provided outside the normal system
locations. See the loader diagnostics if symbol lookup fails.

### 2. Install or select MPICH with Hydra

The recorded local validation used **MPICH 5.0.1**. Use that version to reproduce
the documented setup where possible. An existing MPICH installation is fine
if it includes headers, shared libraries, `mpicc`, `mpicxx`, `mpifort`,
`mpiexec`, and the Hydra process manager. Build both MANA and the applications
with the same selected MPI. Do not accidentally mix MPICH wrappers with an
Open MPI runtime. Other MPI versions require their own validation.

If MPICH is not already installed, the following example installs it in your
home directory, outside the MANA repository:

```bash
export MPICH_HOME="$HOME/opt/mpich/5.0.1"
mkdir -p "$HOME/src" "$HOME/build/mpich-5.0.1"
cd "$HOME/src"
curl -fL https://www.mpich.org/static/downloads/5.0.1/mpich-5.0.1.tar.gz \
  -o mpich-5.0.1.tar.gz
tar -xzf mpich-5.0.1.tar.gz
cd "$HOME/build/mpich-5.0.1"
"$HOME/src/mpich-5.0.1/configure" \
  --prefix="$MPICH_HOME" --enable-shared --with-pm=hydra \
  CC=gcc CXX=g++ FC=gfortran
make -j8
make install
```

This is an installation recipe based on the
[official MPICH 5.0.1 installation guide](https://www.mpich.org/static/downloads/5.0.1/mpich-5.0.1-installguide.pdf),
not a claim that MPICH was rebuilt during this audit. Cluster installations
may need site-specific network/device options or an existing MPI module.
Reduce `-j8` if memory or CPU resources are limited. For an existing installation,
set `MPICH_HOME` to its prefix instead of rebuilding it.

```bash
export PATH="$MPICH_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$MPICH_HOME/lib:${LD_LIBRARY_PATH:-}"
"$MPICH_HOME/bin/mpicc" -show
"$MPICH_HOME/bin/mpifort" -show
"$MPICH_HOME/bin/mpiexec" -info
"$MPICH_HOME/bin/mpiexec" -launcher fork -n 2 hostname
```

The final command checks the launcher, not MPI communication; the native
counter test below checks actual collectives. If your MPI installs libraries
under `lib64`, adjust library paths and linker flags throughout this guide.

### 3. Clone the modified MANA and initialize bundled DMTCP

Replace `YOUR_ACCOUNT` and the branch with the published fork details:

```bash
mkdir -p "$HOME/src"
cd "$HOME/src"
git clone --branch personal-mpich-hydra --recurse-submodules \
  https://github.com/YOUR_ACCOUNT/mana.git mana-personal
cd mana-personal
export MANA_HOME="$PWD"
git submodule update --init --recursive
git -C dmtcp rev-parse HEAD
bash contrib/dmtcp-patches/apply.sh
```

**Do not install a separate system DMTCP for this build.** MANA builds the
version pinned in its `dmtcp/` submodule. This is also how the
[upstream MANA manual](https://github.com/mpickpt/mana/wiki) supplies DMTCP.
Use a Git clone rather than GitHub's source ZIP so submodule initialization
works as shown. Apply the downstream `PMI_FD` patch before compilation and
after resetting/replacing DMTCP. The helper is idempotent.

### 4. Build MANA using the selected MPI

```bash
cd "$MANA_HOME"
export PATH="$MPICH_HOME/bin:$MANA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$MPICH_HOME/lib:${LD_LIBRARY_PATH:-}"

./configure CFLAGS='-O2 -fno-stack-protector' \
            CXXFLAGS='-O2 -fno-stack-protector'
make -j8 mana \
  MPICC="$MPICH_HOME/bin/mpicc" \
  MPICXX="$MPICH_HOME/bin/mpicxx -std=c++14" \
  MPIFORTRAN="$MPICH_HOME/bin/mpifort" \
  MPIRUN="$MPICH_HOME/bin/mpiexec" \
  MPI_LD_FLAG="-L$MPICH_HOME/lib -lmpi"

ldd "$MANA_HOME/bin/lower-half"
test -x "$MANA_HOME/bin/dmtcp_command"
test -f "$MANA_HOME/lib/dmtcp/libmana.so"
```

For this recorded revision, pass MPI overrides to **make**, including later
rebuilds; setting them only in the configure environment does not override
the recorded build definitions. Keep `-fno-stack-protector`. Confirm `ldd`
resolves `libmpi` to your selected installation and reports no missing
libraries. MANA and bundled DMTCP artifacts are placed in this source tree's
`bin/` and `lib/`; no separate `sudo make install` is needed for this workflow.

Do not source the unchanged personal `initialize.sh` on another machine.
Its hardcoded paths would replace the environment selected above. Repeat the
exports in new shells, or put your own paths in a local environment script.

### 5. Verify the installation

Run the regression tests, then the real native and checkpoint/restart tests:

```bash
cd "$MANA_HOME"
python3 ci/test-mana-restart.py -v
python3 ci/test-mana-coordinator.py -v
python3 ci/test-build-id-debug.py -v
python3 ci/multinode/test-verify.py -v

export RUN_BASE="$HOME/mana-test-runs"
mkdir -p "$RUN_BASE"
python3 contrib/checkpoint-tests/run-test.py counter \
  --mode native --ranks 2 --work-base "$RUN_BASE" --run-timeout 120
python3 contrib/checkpoint-tests/run-test.py counter \
  --mode checkpoint --ranks 2 --work-base "$RUN_BASE" \
  --checkpoint-timeout 120 --run-timeout 120
```

Expect the regression suites to pass and the runners to report
`PASS: counter native` and `PASS: counter checkpoint`. The checkpoint runner
starts its own persistent coordinator, requests and waits for complete images,
stops the computation, restarts it, and checks rewind and subsequent collective
results. It keeps logs, `result.json`, and checkpoint images in the printed
directory under `RUN_BASE`; these are local evidence, not GitHub source files.

The integration notes record 30 passing regression tests and a passing local
two-rank checkpoint/restart on the original machine. Those are **historical
results**, not new validation of this incomplete Windows copy. The legacy
MPI unit-test target has stale source dependencies; use the commands above
instead of treating that target as a reliable installation check.

### 6. Optional multi-node use

Each node needs compatible Linux/runtime libraries, the same selected MPICH
and MANA build at the same absolute paths, noninteractive SSH from the launch
node, and a coordinator address/port reachable by every rank. Prepare the
working/checkpoint directories and decide whether storage is shared or local
before running. A hostfile alone does not distribute files.

Use [the multi-node runner instructions](../ci/multinode/README.md) and
[the distributed workflow guide](distributed-mpich-hydra.md). Multi-node
execution and Class D NPB checkpoint/restart were not validated in the
recorded local integration; test them on the intended resources separately.
