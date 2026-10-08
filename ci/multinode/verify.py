#!/usr/bin/env python3
"""Verify rank coverage, rewind, forward progress, and collective arithmetic."""
import re
import sys
from pathlib import Path

PATTERN = re.compile(
    r"rank=(?P<rank>\d+)/(?P<size>\d+) host=(?P<host>\S+) .*?"
    r"iteration=(?P<iteration>\d+) allreduce_sum=(?P<sum>-?\d+)"
)


def parse(path):
    records = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        match = PATTERN.search(line)
        if match:
            records.append({key: value if key == "host" else int(value)
                            for key, value in match.groupdict().items()})
    return records


def verify(launch_path, restart_path, ranks):
    before, after = parse(launch_path), parse(restart_path)
    expected_ranks = set(range(ranks))
    if ranks < 2:
        raise ValueError("Multi-node validation requires at least two ranks")
    for label, records in (("original", before), ("restarted", after)):
        if {record["rank"] for record in records} != expected_ranks:
            raise ValueError(f"Missing or unexpected ranks in {label} output")
        if len({record["host"] for record in records}) < 2:
            raise ValueError(f"Fewer than two distinct hosts in {label} output")
        for record in records:
            expected = ranks * 2 * record["iteration"] + ranks * (ranks - 1) // 2
            if record["size"] != ranks or record["sum"] != expected:
                raise ValueError(f"Incorrect communicator size or Allreduce: {record}")

    rewinds = {}
    for rank in sorted(expected_ranks):
        previous = [record["iteration"] for record in before if record["rank"] == rank]
        resumed = [record["iteration"] for record in after if record["rank"] == rank]
        if resumed[0] >= max(previous):
            raise ValueError(f"Rollback not demonstrated for rank {rank}")
        if max(resumed) <= max(previous):
            raise ValueError(f"No progress beyond original execution for rank {rank}")
        rewinds[rank] = max(previous) - resumed[0]
    return rewinds


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: verify.py LAUNCH_LOG RESTART_LOG RANKS")
    try:
        rewinds = verify(sys.argv[1], sys.argv[2], int(sys.argv[3]))
    except ValueError as error:
        raise SystemExit(str(error))
    print(f"Demonstrated rewind per rank: {rewinds}")
    print("All ranks resumed on multiple hosts and advanced beyond original execution.")
    print("Post-restart MPI_Allreduce: correct")
