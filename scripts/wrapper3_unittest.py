# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for wrapper3"""

import os
from pathlib import Path
import sys
from typing import List, Union

from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import timeout_util


WRAPPER = Path(__file__).resolve().parent / "wrapper3.py"


class FindTargetTests(cros_test_lib.TempDirTestCase):
    """Tests for FindTarget()."""

    def setUp(self):
        # Create a skeleton chromite layout.
        # tmpdir/
        #   chromite/
        #     bin/<wrapper>
        #     scripts/
        #     api -> <real chromite>/api/
        #     lib -> <real chromite>/lib/
        #     utils -> <real chromite>/utils/
        #     __init__.py -> <real chromite>/__init__.py
        #     PRESUBMIT.cfg   # Marker file for our wrapper to find chromite.
        self.chromite_dir = self.tempdir / "chromite"
        self.bindir = self.chromite_dir / "bin"
        self.bindir.mkdir(parents=True)
        self.scripts_dir = self.chromite_dir / "scripts"
        self.scripts_dir.mkdir()
        for subdir in ("api", "cbuildbot", "lib", "third_party", "utils"):
            (self.chromite_dir / subdir).symlink_to(
                constants.CHROMITE_DIR / subdir
            )
        for subfile in ("__init__.py",):
            (self.chromite_dir / subfile).symlink_to(
                constants.CHROMITE_DIR / subfile
            )
        for subfile in ("PRESUBMIT.cfg",):
            (self.chromite_dir / subfile).touch()
        self.wrapper = self.scripts_dir / WRAPPER.name
        # Copy over the wrapper.  We can't just symlink it because the code also
        # walks & resolves symlinks on itself.  Try hardlink at first, but if
        # the tempdir is on a diff mount, fallback to a copy.
        try:
            if sys.version_info >= (3, 8):
                self.wrapper.link_to(WRAPPER)
            else:
                os.link(WRAPPER, self.wrapper)
        except OSError:
            self.wrapper.write_bytes(WRAPPER.read_bytes())
            self.wrapper.chmod(0o755)

    @staticmethod
    def insert_path(var: str, value: str):
        """Insert |value| into the start of the environment |var|."""
        if var in os.environ:
            value += f":{os.environ[var]}"
        os.environ[var] = value

    def gen_script(self, path: Path, wrapper: Path = None):
        """Create a script at |path|."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path = path.with_suffix(".py")
        path.write_text(
            'def main(argv):\n  print("hi", argv)\n', encoding="utf-8"
        )
        if wrapper is None:
            wrapper = path.with_suffix("")
        wrapper.symlink_to(self.wrapper)

    def run_script(self, argv: List[Union[Path, str]], **kwargs):
        """Run |prog| and return the output."""
        # Log the directory layout to help with debugging.
        try:
            cros_build_lib.run(
                ["tree", "-p", str(self.tempdir)],
                encoding="utf-8",
                print_cmd=False,
            )
        except cros_build_lib.RunCommandError:
            pass

        # Helper to include a small timeout in case of bugs.
        with timeout_util.Timeout(30):
            return cros_build_lib.run(
                [str(x) for x in argv],
                capture_output=True,
                encoding="utf-8",
                **kwargs,
            )

    def _run_tests(self, prog: Path, verify=None, **kwargs):
        """Run |prog| in the different fun ways."""
        if verify is None:
            verify = lambda result: self.assertEqual("hi []\n", result.stdout)

        # Execute absolute path.
        result = self.run_script([prog], **kwargs)
        verify(result)

        # Execute ./ relative path.
        result = self.run_script([f"./{prog.name}"], cwd=prog.parent, **kwargs)
        verify(result)

        # Execute ./path/ relative path.
        result = self.run_script(
            [f"./{prog.parent.name}/{prog.name}"],
            cwd=prog.parent.parent,
            **kwargs,
        )
        verify(result)

        # Run via $PATH.
        self.insert_path("PATH", str(prog.parent))
        result = self.run_script([prog.name], **kwargs)
        verify(result)

    def testExternal(self):
        """Verify use from outside of chromite/ works with main() scripts."""
        prog = self.tempdir / "path" / "prog"
        self.gen_script(prog)
        self._run_tests(prog)

    def testChromiteBin(self):
        """Verify chromite/bin/ works with module in chromite/scripts/."""
        prog = self.bindir / "prog"
        self.gen_script(self.scripts_dir / prog.name, prog)
        self._run_tests(prog)

    def testChromiteScripts(self):
        """Verify chromite/scripts/ works with main() scripts."""
        prog = self.scripts_dir / "prog"
        self.gen_script(prog)
        self._run_tests(prog)

    def testChromiteCustomdir(self):
        """Verify chromite/customdir/ works with main() scripts."""
        prog = self.chromite_dir / "customdir" / "prog"
        self.gen_script(prog)
        self._run_tests(prog)

    def testChromiteTopdir(self):
        """Verify chromite/ works with main() scripts."""
        prog = self.chromite_dir / "prog"
        self.gen_script(prog)
        self._run_tests(prog)

    def testWrapper(self):
        """Fail quickly when running the wrapper directly."""
        verify = lambda result: self.assertEqual(result.returncode, 100)
        self._run_tests(self.wrapper, verify=verify, check=False)

    def testMissingScript(self):
        """Fail quickly if wrapped script is missing."""
        verify = lambda result: self.assertNotEqual(result.returncode, 0)
        prog = self.bindir / "prog"
        prog.symlink_to(self.wrapper)
        self._run_tests(prog, verify=verify, check=False)

    def testBrokenScript(self):
        """Fail quickly if wrapped script is corrupt."""
        verify = lambda result: self.assertNotEqual(result.returncode, 0)
        prog = self.scripts_dir / "prog"
        prog.symlink_to(self.wrapper)
        # Script has syntax errors and cannot be imported.
        prog.with_suffix(".py").write_text("}", encoding="utf-8")
        self._run_tests(prog, verify=verify, check=False)

    def testDashes(self):
        """Check behavior of scripts with dashes in their names."""
        script = self.chromite_dir / "scripts" / "p_r_o_g"
        self.gen_script(script)
        prog = self.chromite_dir / "bin" / "p-r-o-g"
        prog.symlink_to(self.wrapper)
        self._run_tests(prog)
