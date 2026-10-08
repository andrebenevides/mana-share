#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path

from verify import verify


class VerifyTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mana-log-verify-")
        self.addCleanup(temp.cleanup)
        self.before = Path(temp.name) / "before.log"
        self.after = Path(temp.name) / "after.log"
        self.before.write_text(self.records(range(10)))
        self.after.write_text(self.records(range(5, 15)))

    @staticmethod
    def records(iterations, ranks=range(2), shared_host=False):
        return "".join(
            f"rank={rank}/2 host=node{0 if shared_host else rank} pid=42 "
            f"iteration={iteration} allreduce_sum={4 * iteration + 1}\n"
            for iteration in iterations for rank in ranks
        )

    def test_valid_restart(self):
        self.assertEqual(verify(self.before, self.after, 2), {0: 4, 1: 4})

    def test_missing_rank(self):
        self.after.write_text(self.records(range(5, 15), ranks=[0]))
        with self.assertRaisesRegex(ValueError, "Missing"):
            verify(self.before, self.after, 2)

    def test_no_rewind(self):
        self.after.write_text(self.records(range(9, 15)))
        with self.assertRaisesRegex(ValueError, "Rollback"):
            verify(self.before, self.after, 2)

    def test_no_progress(self):
        self.after.write_text(self.records(range(5, 8)))
        with self.assertRaisesRegex(ValueError, "No progress"):
            verify(self.before, self.after, 2)

    def test_incorrect_collective(self):
        self.after.write_text(self.after.read_text().replace("allreduce_sum=21", "allreduce_sum=0"))
        with self.assertRaisesRegex(ValueError, "Allreduce"):
            verify(self.before, self.after, 2)

    def test_single_host(self):
        self.after.write_text(self.records(range(5, 15), shared_host=True))
        with self.assertRaisesRegex(ValueError, "two distinct hosts"):
            verify(self.before, self.after, 2)


if __name__ == "__main__":
    unittest.main()
