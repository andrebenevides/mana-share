# Local integration of the distributed MPICH/Hydra changes

Reviewed and integrated on 2026-09-21 against MANA
`f296e33267598d12bc0886f67774e20dda58c77e` and bundled DMTCP
`ff8e28969def414dcc5e51ae611412ca389b759f`, following `desc.md` and
[umbrella issue #485](https://github.com/mpickpt/mana/issues/485).

## Decisions

All six contributions are useful for the intended Ubuntu/MPICH workflow.
The runtime changes are integrated below; multi-node testing remains opt-in.

| PR / reviewed commit | Integration and relevance |
| --- | --- |
| [#486](https://github.com/mpickpt/mana/pull/486), `7aafe1b3d3b6895ce5f6488b8b902b3b116c8263` | Resolve restart directories independently of the caller's working directory, reject incomplete checkpoints, and put the rank image last. Useful on a single machine as well as a cluster. Additional fixes preserve arguments containing spaces and correctly check coordinator failure. |
| [#487](https://github.com/mpickpt/mana/pull/487), `c992152568d1253abbaf674c21d86a739ff84f0f` | Add `mana_coordinator --persistent`, retaining exit-on-last as the default. Useful when reusing a coordinator across MPI launches. Help documents the flag and argument boundaries are preserved. Runtime testing also exposed and fixed a status-file startup race; launch/restart readers tolerate blank lines. |
| [#488](https://github.com/mpickpt/mana/pull/488), `99571b3d3478326e1de538721df62be58a3a4f58` | Locate detached ELF64 loader symbols by GNU build ID, with `MANA_DEBUG_ROOT` support. Relevant to Ubuntu's `libc6-dbg` layout. The existing symbol reader now allows fallback rather than aborting first; the new resolver is independently testable and validates ELF bounds/encoding. |
| [#489](https://github.com/mpickpt/mana/pull/489), `fed39e713d29b23dc5e60c749293cbef036a4430` | Add the MPI counter workload and opt-in Hydra/SSH test. The integrated runner uses unique directories, tracks its own launchers, handles shared-file copies, bounds operations, and requires every rank on multiple hosts to demonstrate strict rewind, correct collectives, and progress. |
| [#490](https://github.com/mpickpt/mana/pull/490), `f76b110c3782f5b1773dd8b1ea060c770dfb27db` | Add the distributed workflow guide, updated to describe the integrated features and working build commands. This revision requires MPI tool overrides on `make`; supplying them only through the configure environment is ineffective. |
| [#491](https://github.com/mpickpt/mana/pull/491), `7c3218629f4cb5f733f9d97c74b3c1b902b66c52` | Carry and apply the proposed `PMI_FD` compatibility patch to the checked-out DMTCP source. This skips the whole pre-existing socket scan under that environment variable, matching the existing MPI exceptions. It remains a downstream change whose upstream ownership is unresolved. |

The PRs were independent branches. Their additions to `ci/unit-test.sh` were
combined and moved before the MPI build, using paths based on the script's
directory. The original additions would have run from the wrong directory.

## Build and validation on this machine

Environment: Ubuntu 22.04.5, MPICH 5.0.1 installed at
`/home/andre_benevides/opt/mpich/5.0.1`, and `libc6-dbg` installed.

The full build succeeded with:

```bash
export MPICH_HOME=/home/andre_benevides/opt/mpich/5.0.1
bash contrib/dmtcp-patches/apply.sh
./configure CFLAGS='-O2 -fno-stack-protector' \
            CXXFLAGS='-O2 -fno-stack-protector'
make -j8 mana \
  MPICC="$MPICH_HOME/bin/mpicc" \
  MPICXX="$MPICH_HOME/bin/mpicxx -std=c++14" \
  MPIFORTRAN="$MPICH_HOME/bin/mpifort" \
  MPIRUN="$MPICH_HOME/bin/mpiexec" \
  MPI_LD_FLAG="-L$MPICH_HOME/lib -lmpi"
```

The executables are available under `bin/` in this checkout. No system-wide
installation was performed. `ldd bin/lower-half` resolves MPI to the selected
installation without missing libraries.

Validation completed:

- 30 local regression tests passed: 10 restart-wrapper tests, 6 coordinator
  tests, 8 ELF/debug-symbol tests, and 6 distributed-log verifier tests.
- Native two-rank MPICH execution passed with correct `MPI_Allreduce` output.
- A two-rank MANA run on this host checkpointed into two non-empty images,
  stopped, and restarted from an unrelated working directory with other
  options after `--restartdir`. Both ranks rewound, advanced past their original
  progress, and produced correct collective results. The persistent
  coordinator remained available across the zero-client interval.
- The DMTCP patch helper was run repeatedly and correctly detected the
  already-applied patch.
- Shell syntax and Git whitespace checks passed. The multi-node runner
  returned a successful skip with no `MANA_TEST_HOSTFILE`.

Re-run the local regression tests with:

```bash
python3 ci/test-mana-restart.py -v
python3 ci/test-mana-coordinator.py -v
python3 ci/test-build-id-debug.py -v
python3 ci/multinode/test-verify.py -v
```

The pre-existing MPI unit-test Makefile fails with
`No rule to make target 'record-replay-comm-test.exe'` because its link rule
still references removed `split_process` and `procmapsutils` sources. Those
older tests were not repaired as part of these PRs. This is separate from the
successful full build and runtime checkpoint/restart test.

Multi-node SSH execution was not run: no cluster hostfile was supplied.
See [the distributed guide](distributed-mpich-hydra.md) and
[runner options](../ci/multinode/README.md) to validate on the intended nodes.
The bundled `dmtcp_command --bcheckpoint` returned before images were complete
in local testing; the runner explicitly waits for non-empty images and no
remaining `.tmp` files instead of relying solely on that return code.

Build and test evidence from this session is under `/tmp/mana-pr-review/`;
the successful runtime run is `runtime-jzhh268e/`. These temporary files are
not needed to build the repository and may disappear on reboot.

## Keeping the DMTCP change

The submodule remains pinned to the original upstream commit, with a local
modification in `dmtcp/src/plugin/ipc/socket/socketconnlist.cpp`. A parent
repository commit alone does not capture that modified submodule source.
The tracked patch/helper under `contrib/dmtcp-patches/` makes it reproducible:
run `bash contrib/dmtcp-patches/apply.sh` after initializing or resetting
DMTCP and before rebuilding. No commits or remote branches were created.
