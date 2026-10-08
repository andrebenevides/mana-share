# Required Hydra `PMI_FD` downstream patch

This directory records the exact DMTCP source delta required by the contributor's validated MANA/MPICH/Hydra environment.

Apply locally for testing:

```bash
bash contrib/dmtcp-patches/apply.sh
```

The helper modifies only the checked-out DMTCP submodule source and is idempotent.
Run it before building MANA for MPICH/Hydra, including after resetting or
replacing the submodule. A second invocation reports that the patch is applied.
The parent repository still references the original upstream DMTCP commit;
`git status` reports the locally modified submodule. Keeping this patch and
helper in the parent repository makes the modification reproducible.

The condition skips the entire pre-existing socket scan when `PMI_FD` is set,
matching the existing Slurm/Hydra exceptions. It does not selectively ignore
only that descriptor. This is a downstream compatibility fix for the workflow
reported in [MANA PR #491](https://github.com/mpickpt/mana/pull/491), whose
multi-node behavior must still be validated in the target environment.

This draft intentionally asks the MANA maintainers to decide whether the final solution should be a temporary downstream patch, an in-tree MANA compatibility fix, a direct DMTCP contribution, or another design.
