#!/usr/bin/env python3
"""Exercise detached ELF symbol lookup without MPI or system debug-file writes."""
import os
import re
import shlex
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "mpi-proxy-split" / "lower-half"


class BuildIdDebugTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="mana-build-id-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        harness = cls.root / "lookup.cpp"
        harness.write_text('''#include "build-id-debug.h"
#include <iostream>
int main(int argc, char **argv) {
  if (argc < 2) return 2;
  if (argc == 4) {
    std::cout << get_symbol_offset_with_debug(argv[1], argv[3]) << "\\n";
  } else {
    std::cout << get_build_id_debug_path(argv[1], argc == 3 ? argv[2] : nullptr)
              << "\\n";
  }
}
''', encoding="utf-8")
        cls.lookup = cls.root / "lookup"
        subprocess.run(shlex.split(os.environ.get("CXX", "g++")) + [
            "-std=c++14", "-g", "-I", str(SOURCE), str(harness),
            str(SOURCE / "build-id-debug.cpp"),
            str(SOURCE / "get-symbol-offset.c"), "-o", str(cls.lookup)
        ], check=True)
        fixture = cls.root / "fixture.c"
        fixture.write_text("int mana_probe(void) { return 42; }\n"
                           "int main(void) { return mana_probe(); }\n")
        cls.elf = cls.root / "fixture"
        subprocess.run(["gcc", "-g", "-Wl,--build-id=sha1", str(fixture),
                        "-o", str(cls.elf)], check=True)
        notes = subprocess.check_output(["readelf", "-n", str(cls.elf)], text=True)
        cls.build_id = re.search(r"Build ID: ([0-9a-f]+)", notes).group(1)
        cls.debug_root = cls.root / "debug files"
        cls.debug_path = (cls.debug_root / ".build-id" / cls.build_id[:2] /
                          (cls.build_id[2:] + ".debug"))
        cls.debug_path.parent.mkdir(parents=True)
        subprocess.run(["objcopy", "--only-keep-debug", str(cls.elf),
                        str(cls.debug_path)], check=True)
        symbols = subprocess.check_output(["nm", str(cls.elf)], text=True)
        cls.symbol = int(re.search(r"([0-9a-f]+) T mana_probe", symbols).group(1), 16)
        cls.stripped = cls.root / "stripped"
        shutil.copy2(cls.elf, cls.stripped)
        subprocess.run(["strip", "--strip-all", str(cls.stripped)], check=True)
        subprocess.run(["objcopy", "--add-gnu-debuglink=" + str(cls.debug_path),
                        str(cls.stripped)], check=True)

    def run_lookup(self, *args, **kwargs):
        return subprocess.check_output([str(self.lookup), *map(str, args)],
                                       text=True, timeout=10, **kwargs).strip()

    def test_matches_readelf(self):
        self.assertEqual(self.run_lookup(self.elf, str(self.debug_root) + "///"),
                         str(self.debug_path))

    def test_symlink(self):
        link = self.root / "loader-link"
        link.symlink_to(self.elf.name)
        self.assertEqual(self.run_lookup(link, self.debug_root), str(self.debug_path))

    def test_environment_override(self):
        env = dict(os.environ, MANA_DEBUG_ROOT=str(self.debug_root))
        self.assertEqual(self.run_lookup(self.elf, env=env), str(self.debug_path))
        self.assertTrue(self.run_lookup(self.elf, "/explicit", env=env)
                        .startswith("/explicit/.build-id/"))

    def test_default_root(self):
        env = os.environ.copy()
        env.pop("MANA_DEBUG_ROOT", None)
        self.assertTrue(self.run_lookup(self.elf, env=env)
                        .startswith("/usr/lib/debug/.build-id/"))

    def test_embedded_symbols(self):
        self.assertEqual(int(self.run_lookup(self.elf, "unused", "mana_probe")),
                         self.symbol)

    def test_detached_symbol_fallback(self):
        env = dict(os.environ, MANA_DEBUG_ROOT=str(self.debug_root))
        self.assertEqual(int(self.run_lookup(self.stripped, "unused", "mana_probe",
                                            env=env)), self.symbol)

    def test_missing_and_non_elf(self):
        self.assertEqual(self.run_lookup(self.root / "missing"), "")
        self.assertEqual(self.run_lookup(self.root / "fixture.c"), "")

    def test_invalid_elf_headers(self):
        original = self.elf.read_bytes()
        mutations = []
        wrong_class = bytearray(original)
        wrong_class[4] = 1
        mutations.append(wrong_class)
        wrong_endian = bytearray(original)
        wrong_endian[5] = 2 if original[5] == 1 else 1
        mutations.append(wrong_endian)
        bad_offset = bytearray(original)
        struct.pack_into("=Q", bad_offset, 32, 2**64 - 1)
        mutations.extend([bad_offset, original[:32]])
        for index, contents in enumerate(mutations):
            with self.subTest(index=index):
                elf = self.root / ("invalid-" + str(index))
                elf.write_bytes(contents)
                self.assertEqual(self.run_lookup(elf), "")


if __name__ == "__main__":
    unittest.main()
