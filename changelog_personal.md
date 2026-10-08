# Changelog

## 21/09/2026

Integrated the six PRs listed in `desc.md`, with the following local adjustments.

- **Restart paths — PR #486:** Resolve `--restartdir` independently of the
  working directory, detect incomplete checkpoints, and place the restart image
  after other options. Files: `bin/mana_restart`, `ci/test-mana-restart.py`.
  **Beyond the PR:** Preserve arguments containing spaces, handle missing values
  before another option, correctly check coordinator failure, and expand tests.

- **Persistent coordinator — PR #487:** Add `--persistent` while retaining
  exit-on-last as the default. Files: `bin/mana_coordinator`,
  `ci/test-mana-coordinator.py`.
  **Beyond the PR:** Document the option in help, preserve argument boundaries
  using Bash arrays, wait for complete coordinator status, and test delayed
  startup. Also tolerate blank status-file lines in `bin/mana_launch` and
  `bin/mana_restart` to fix the startup race found during runtime testing.

- **Loader debug symbols — PR #488:** Find detached symbols by GNU build ID,
  including through `MANA_DEBUG_ROOT`. Files under `mpi-proxy-split/lower-half/`:
  `build-id-debug.cpp`, `build-id-debug.h`, `lower-half.cpp`, and `Makefile`.
  **Beyond the PR:** Extract the resolver for standalone testing, validate ELF
  bounds and encoding, handle interrupted reads, resolve conventional paths
  through `realpath`, and improve failure diagnostics. Update
  `get-symbol-offset.c` so legacy lookup permits fallback, closes resources,
  and bounds path construction. Add `ci/test-build-id-debug.py`.

- **Multi-node test — PR #489:** Add `ci/multinode/mpi_counter.c`,
  `run-mpich-hydra.sh`, and `README.md` for opt-in Hydra/SSH checkpoint/restart.
  **Beyond the PR:** Use unique run directories, stop tracked launchers instead
  of matching arbitrary processes, support shared-file copies and remote-user
  selection, add timeouts and input checks, and wait for complete status files.
  Add `ci/multinode/verify.py` and `test-verify.py` to require every rank on
  multiple hosts to demonstrate strict rewind, correct collectives, and
  progress beyond the original execution.

- **Workflow documentation — PR #490:** Add `doc/distributed-mpich-hydra.md`
  and link it from `README.md`.
  **Beyond the PR:** Describe the integrated features, correct MPI tool
  overrides to be passed to `make`, update runner instructions, and add
  `doc/local-pr-integration.md` with review decisions and validation results.

- **Hydra compatibility — PR #491:** Add the patch, `apply.sh`, and `README.md`
  under `contrib/dmtcp-patches/`.
  **Beyond the PR:** Apply the `PMI_FD` condition locally to
  `dmtcp/src/plugin/ipc/socket/socketconnlist.cpp`, retain the upstream submodule
  commit, and make the helper detect the exact applied patch using reverse
  checks. Document how to reproduce the local submodule modification.

- **Integration changes beyond the PRs:** Combine regression checks in
  `ci/unit-test.sh`, run them before the MPI build, and fix their working-directory
  dependencies. Update `.gitignore` to exclude the generated lower-half binary.

Validation: full build with MPICH 5.0.1, 30 regression tests, and local two-rank
checkpoint/restart passed. Multi-node execution awaits a hostfile; the older
MPI unit-test target remains blocked by stale source references. See
[the integration notes](doc/local-pr-integration.md) for details.
