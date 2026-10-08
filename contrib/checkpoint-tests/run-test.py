#!/usr/bin/env python3
"""Run the documented counter or NPB test, retaining logs and checkpoint images.

Single-host MPICH by default. --hostfile requires a shared work directory and
identical MANA, MPICH, and executable paths on every host (see desc.md).
"""
import argparse
import json
import math
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COUNTER = re.compile(r"rank=(\d+)/(\d+) .*?iteration=(\d+) allreduce_sum=(-?\d+)")


def read_log(path):
    return path.read_text(errors="replace") if path.exists() else ""


def progress(path, kind):
    text = read_log(path)
    if kind == "counter":
        result = {}
        for rank, size, iteration, total in COUNTER.findall(text):
            result.setdefault(int(rank), []).append(int(iteration))
        return result
    pattern = (r"^\s*Time step\s+(\d+)" if kind == "bt" else
               r"^\s*(\d+)\s+[+-]?[\d.]+[EDed][+-]?\d+\s+[+-]?[\d.]+\s*$")
    return {0: [int(n) for n in re.findall(pattern, text, re.MULTILINE)]}


def verify_output(path, args):
    text = read_log(path)
    if args.kind == "counter":
        records = [tuple(map(int, record)) for record in COUNTER.findall(text)]
        if {record[0] for record in records} != set(range(args.ranks)):
            raise RuntimeError("Missing counter ranks in " + str(path))
        for rank, size, iteration, total in records:
            expected = args.ranks * 2 * iteration + args.ranks * (args.ranks - 1) // 2
            if size != args.ranks or total != expected:
                raise RuntimeError("Incorrect MPI_Allreduce result in " + str(path))
    else:
        checks = [r"Verification\s*=\s*SUCCESSFUL\b",
                  rf"Class\s*=\s*{args.npb_class}\b",
                  rf"Total processes\s*=\s*{args.ranks}\b",
                  rf"Active processes\s*=\s*{args.ranks}\b"]
        if not all(re.search(pattern, text) for pattern in checks):
            raise RuntimeError("NPB verification/class/rank check failed: " + str(path))


class TestRun:
    def __init__(self, args):
        self.args = args
        self.mana = Path(os.environ.get("MANA_HOME", ROOT)).resolve()
        self.mpich = Path(os.environ["MPICH_HOME"]).resolve()
        base = Path(args.work_base).resolve()
        base.mkdir(parents=True, exist_ok=True)
        for path in (self.mana, self.mpich, base):
            if re.search(r"\s", str(path)):
                raise ValueError("Use paths without whitespace: " + str(path))
        self.work = Path(tempfile.mkdtemp(prefix=f"mana-{args.kind}-", dir=base))
        for name in ("home", "checkpoints", "tmp", "logs"):
            (self.work / name).mkdir()
        self.coord = []
        self.process = None
        self.env = os.environ.copy()
        self.env.update(HOME=str(self.work / "home"), OMP_NUM_THREADS="1",
                        GFORTRAN_UNBUFFERED_ALL="y", NPB_NPROCS_STRICT="1")
        for name in ("SLURM_JOB_ID", "SLURM_JOBID"):
            self.env.pop(name, None)
        self.env["PATH"] = f"{self.mana}/bin:{self.mpich}/bin:" + self.env.get("PATH", "")
        self.env["LD_LIBRARY_PATH"] = (
            f"{self.mana}/lib:{self.mana}/lib/dmtcp:{self.mpich}/lib:"
            + self.env.get("LD_LIBRARY_PATH", "")
        )
        self.mpi = [str(self.mpich / "bin/mpiexec"), "-launcher",
                    "ssh" if args.hostfile else "fork", "-wdir", str(self.work),
                    "-n", str(args.ranks), "-genv", "HOME", str(self.work / "home"),
                    "-genv", "GFORTRAN_UNBUFFERED_ALL", "y",
                    "-genv", "NPB_NPROCS_STRICT", "1"]
        if args.hostfile:
            self.mpi += ["-f", str(Path(args.hostfile).resolve())]
        self.result = {"kind": args.kind, "mode": args.mode, "ranks": args.ranks,
                       "class": None if args.kind == "counter" else args.npb_class,
                       "workdir": str(self.work)}

    def run(self, command, timeout=30):
        result = subprocess.run(list(map(str, command)), env=self.env, cwd=self.work,
                                text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout)
        if result.returncode:
            raise RuntimeError(f"Command failed ({result.returncode}): {command}\n{result.stdout}")
        return result.stdout

    def control(self, option, timeout=30):
        return self.run([self.mana / "bin/dmtcp_command", *self.coord, option], timeout)

    def start(self, command, log):
        with log.open("w") as output:
            self.process = subprocess.Popen(list(map(str, command)), cwd=self.work,
                                            env=self.env, stdout=output,
                                            stderr=subprocess.STDOUT, start_new_session=True)

    def wait_for(self, predicate, timeout, label, allow_completion=False):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            if self.process is not None and self.process.poll() is not None:
                if allow_completion and self.process.returncode == 0:
                    return
                raise RuntimeError(f"Application exited while waiting for {label}; inspect logs. "
                                   "If it completed successfully before checkpointing, use a larger class.")
            time.sleep(0.1)
        raise RuntimeError("Timed out waiting for " + label)

    def stop_launcher(self):
        if self.process is None:
            return
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait()
        self.process = None

    def images_complete(self):
        ckpt = self.work / "checkpoints"
        if list(ckpt.rglob("*.tmp")):
            return False
        return all(any(p.stat().st_size > 0 for p in
                       (ckpt / f"ckpt_rank_{rank}").glob("*.dmtcp"))
                   for rank in range(self.args.ranks))

    def execute(self):
        args = self.args
        print("Evidence directory:", self.work, flush=True)
        if args.kind == "counter":
            executable = self.work / "mpi_counter"
            self.run([self.mpich / "bin/mpicc", "-O2", "-g", "-Wall", "-Wextra",
                      ROOT / "ci/multinode/mpi_counter.c", "-o", executable])
            app = [executable, "5" if args.mode == "native" else "0", self.work / "logs"]
        else:
            app = [Path(args.exe).resolve()]
            if not app[0].is_file() or re.search(r"\s", str(app[0])):
                raise ValueError("Provide an existing executable with no whitespace in its path")
        self.result["executable"] = str(app[0])
        if args.mode == "native":
            log = self.work / "native.log"
            self.start(self.mpi + app, log)
            if self.process.wait(timeout=args.run_timeout) != 0:
                raise RuntimeError("Native MPI execution failed; see " + str(log))
            verify_output(log, args)
            return

        self.run([self.mana / "bin/mana_coordinator", "--persistent", "--port", "0",
                  "--interval", "0", "--ckptdir", self.work / "checkpoints",
                  "--coord-logfile", self.work / "coordinator.log"])
        status = (self.work / "home/.mana.rc").read_text()
        self.coord = ["-h", re.search(r"^Host:\s+(\S+)", status, re.MULTILINE).group(1),
                      "-p", re.search(r"^Port:\s+(\d+)", status, re.MULTILINE).group(1)]
        flags = ["--ckptdir", self.work / "checkpoints", "--tmpdir", self.work / "tmp"]
        launch_log, restart_log = self.work / "launch.log", self.work / "restart.log"
        self.start(self.mpi + [self.mana / "bin/mana_launch", *flags, *app], launch_log)
        self.wait_for(lambda: re.search(rf"NUM_PEERS={args.ranks}\b", self.control("--status")),
                      args.checkpoint_timeout, "all coordinator peers")
        expected = set(range(args.ranks)) if args.kind == "counter" else {0}

        def started():
            samples = progress(launch_log, args.kind)
            return set(samples) == expected and all(values and max(values) >=
                (3 if args.kind == "counter" else 1) for values in samples.values())

        self.wait_for(started, args.checkpoint_timeout, "application progress")
        if args.checkpoint_delay:
            time.sleep(args.checkpoint_delay)
        print("Requesting checkpoint...", flush=True)
        start = time.monotonic()
        self.control("--bcheckpoint", args.checkpoint_timeout)
        # This bundled command may return before the image files are complete.
        self.wait_for(self.images_complete, args.checkpoint_timeout, "complete checkpoint images")
        self.result["checkpoint_seconds"] = time.monotonic() - start
        saved_progress = progress(launch_log, args.kind)

        def advanced():
            current = progress(launch_log, args.kind)
            return all(len({v for v in current.get(rank, []) if v > max(values)}) >= 2
                       for rank, values in saved_progress.items() if values)

        # Advance beyond the saved state to make rollback visible in the logs.
        self.wait_for(advanced, args.run_timeout, "post-checkpoint progress", allow_completion=True)
        if self.process.poll() is not None:
            verify_output(launch_log, args)
        else:
            self.control("--kill")
        self.stop_launcher()
        before = progress(launch_log, args.kind)
        self.wait_for(lambda: "NUM_PEERS=0" in self.control("--status"), 30, "zero peers")
        print("Restarting from", self.work / "checkpoints", flush=True)
        self.start(self.mpi + [self.mana / "bin/mana_restart", "--restartdir",
                              self.work / "checkpoints", *flags], restart_log)
        if args.kind == "counter":
            self.wait_for(lambda: all(max(progress(restart_log, args.kind).get(rank, [-1]))
                                      > max(before[rank]) for rank in expected),
                          args.run_timeout, "resumed counter progress")
            self.control("--kill")
            self.stop_launcher()
        elif self.process.wait(timeout=args.run_timeout) != 0:
            raise RuntimeError("Restarted benchmark failed; see " + str(restart_log))
        verify_output(restart_log, args)
        after = progress(restart_log, args.kind)
        for rank in expected:
            resumed = after.get(rank, [])
            if not resumed or resumed[0] >= max(before[rank]):
                raise RuntimeError("Numerical output passed, but logs do not demonstrate rewind. "
                                   "Checkpoint earlier or use a larger class.")
            if max(resumed) < max(before[rank]):
                raise RuntimeError("Restart did not recover the original progress")
        self.result["original_last_progress"] = {r: max(v) for r, v in before.items()}
        self.result["restart_first_progress"] = {r: v[0] for r, v in after.items()}
        self.result["restart_last_progress"] = {r: max(v) for r, v in after.items()}

    def cleanup(self):
        if self.coord:
            for option in ("--kill", "--quit"):
                try:
                    self.control(option, 10)
                except (RuntimeError, subprocess.TimeoutExpired) as error:
                    print("Cleanup:", error, file=sys.stderr)
        self.stop_launcher()
        (self.work / "result.json").write_text(json.dumps(self.result, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("counter", "bt", "cg"))
    parser.add_argument("--mode", choices=("native", "checkpoint"), default="checkpoint")
    parser.add_argument("--exe", help="NPB binary, e.g. /path/to/bin/bt.D.x")
    parser.add_argument("--class", dest="npb_class", choices=list("SWABCDEF"), default="D")
    parser.add_argument("--ranks", type=int, default=2)
    parser.add_argument("--work-base", default="/tmp")
    parser.add_argument("--hostfile", help="SSH launch; work-base must be on shared storage")
    parser.add_argument("--checkpoint-delay", type=float, default=0,
                        help="seconds after initial progress before requesting a checkpoint")
    parser.add_argument("--checkpoint-timeout", type=float, default=300)
    parser.add_argument("--run-timeout", type=float, default=3600)
    args = parser.parse_args()
    if not os.environ.get("MPICH_HOME"):
        parser.error("Set MPICH_HOME to the MPI installation used to build MANA")
    if args.ranks < 1 or args.checkpoint_delay < 0 or min(args.checkpoint_timeout, args.run_timeout) <= 0:
        parser.error("Use positive ranks/timeouts and a non-negative checkpoint delay")
    if args.kind != "counter" and not args.exe:
        parser.error("BT/CG require --exe")
    if args.kind == "bt" and math.isqrt(args.ranks) ** 2 != args.ranks:
        parser.error("BT requires a square rank count: 1, 4, 9, 16, ...")
    if args.kind == "cg" and args.ranks & (args.ranks - 1):
        parser.error("CG requires a power-of-two rank count: 1, 2, 4, 8, ...")
    def interrupted(signum, frame):
        raise KeyboardInterrupt("Received termination signal")
    signal.signal(signal.SIGTERM, interrupted)
    run = TestRun(args)
    try:
        run.execute()
        run.result["passed"] = True
        print("PASS:", args.kind, args.mode, flush=True)
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        run.result.update(passed=False, error=str(error))
        print("FAIL:", error, "\nEvidence:", run.work, file=sys.stderr)
        return 1
    finally:
        run.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
