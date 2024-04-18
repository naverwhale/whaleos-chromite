# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Autotest utilities."""

import os
from typing import Optional

from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.utils import matching


class AutotestTarballBuilder:
    """Builds autotest tarballs for testing."""

    # Archive file names.
    _CONTROL_FILES_ARCHIVE = "control_files.tar"
    _PACKAGES_ARCHIVE = "autotest_packages.tar"
    _TEST_SUITES_ARCHIVE = "test_suites.tar.bz2"
    _SERVER_PACKAGE_ARCHIVE = "autotest_server_package.tar.bz2"
    _AUTOTEST_ARCHIVE = "autotest.tar.bz2"

    # Directory within _SERVER_PACKAGE_ARCHIVE where Tast files needed to run
    # with Server-Side Packaging are stored.
    _TAST_SSP_SUBDIR = "tast"

    # Tast files and directories to include in AUTOTEST_SERVER_PACKAGE relative
    # to the build root.
    _TAST_SSP_CHROOT_FILES = [
        "/usr/bin/tast",  # Main Tast executable.
        "/usr/bin/remote_test_runner",  # Runs remote tests.
        "/usr/libexec/tast/bundles",  # Dir containing test bundles.
        "/usr/share/tast/data",  # Dir containing test data.
        "/etc/tast/vars",  # Secret variables.
    ]
    # Tast files and directories stored in the source code.
    _TAST_SSP_SOURCE_FILES = [
        "src/platform/tast/tools/run_tast.sh",  # Helper script to run SSP tast.
    ]

    def __init__(
        self,
        archive_basedir: str,
        output_directory: str,
        chroot: chroot_lib.Chroot,
    ) -> None:
        """Init function.

        Args:
            archive_basedir: The base directory from which the archives will be
                created. This path should contain the `autotest` directory.
            output_directory: The directory where the archives will be written.
            chroot: The Chroot to work with.
        """
        self.archive_basedir = archive_basedir
        self.output_directory = output_directory
        self.chroot = chroot

    def BuildAutotestControlFilesTarball(self) -> Optional[str]:
        """Tar up the autotest control files.

        Returns:
            Path of the partial autotest control files tarball if created.
        """
        # Find the control files in autotest/.
        input_list = matching.FindFilesMatching(
            "control*",
            target="autotest",
            cwd=self.archive_basedir,
            exclude_dirs=["autotest/test_suites"],
        )
        tarball = os.path.join(
            self.output_directory, self._CONTROL_FILES_ARCHIVE
        )
        if self._BuildTarball(input_list, tarball, compressed=False):
            return tarball
        else:
            return None

    def BuildAutotestPackagesTarball(self):
        """Tar up the autotest packages.

        Returns:
            str|None - Path of the partial autotest packages tarball if created.
        """
        input_list = ["autotest/packages"]
        tarball = os.path.join(self.output_directory, self._PACKAGES_ARCHIVE)
        if self._BuildTarball(input_list, tarball, compressed=False):
            return tarball
        else:
            return None

    def BuildAutotestTestSuitesTarball(self):
        """Tar up the autotest test suite control files.

        Returns:
            str|None - Path of the autotest test suites tarball if created.
        """
        input_list = ["autotest/test_suites"]
        tarball = os.path.join(self.output_directory, self._TEST_SUITES_ARCHIVE)
        if self._BuildTarball(input_list, tarball):
            return tarball
        else:
            return None

    def BuildAutotestServerPackageTarball(self) -> Optional[str]:
        """Tar up the autotest files required by the server package.

        Returns:
            The path of the autotest server package tarball if created.
        """
        # Find all files in autotest excluding certain directories.
        tast_files, transforms = self._GetTastServerFilesAndTarTransforms()
        autotest_files = matching.FindFilesMatching(
            "*",
            target="autotest",
            cwd=self.archive_basedir,
            exclude_dirs=(
                "autotest/packages",
                "autotest/client/deps/",
                "autotest/client/tests",
                "autotest/client/site_tests",
            ),
        )

        tarball = os.path.join(
            self.output_directory, self._SERVER_PACKAGE_ARCHIVE
        )
        if self._BuildTarball(
            autotest_files + tast_files,
            tarball,
            extra_args=transforms,
            check=False,
        ):
            return tarball
        else:
            return None

    def BuildAutotestTarball(self):
        """Tar up the full autotest directory.

        Returns:
            str|None - The path of the autotest tarball if created.
        """

        input_list = ["autotest/"]
        tarball = os.path.join(self.output_directory, self._AUTOTEST_ARCHIVE)
        if self._BuildTarball(input_list, tarball):
            return tarball
        else:
            return None

    def _BuildTarball(
        self, input_list, tarball_path, compressed=True, **kwargs
    ):
        """Tars and zips files and directories from input_list to tarball_path.

        Args:
            input_list: A list of files and directories to be archived.
            tarball_path: Path of output tar archive file.
            compressed: Whether the tarball should be compressed with pbzip2.
            **kwargs: Keyword arguments to pass to CreateTarball.

        Returns:
            Return value of cros_build_lib.CreateTarball.
        """
        for pathname in input_list:
            if os.path.exists(os.path.join(self.archive_basedir, pathname)):
                break
        else:
            # If any of them exist we can create an archive, but if none
            # do then we need to stop. For now, since we either pass in a
            # handful of directories we don't necessarily check, or actually
            # search the filesystem for lots of files, this is far more
            # efficient than building out a list of files that do exist.
            return None

        compressor = cros_build_lib.CompressionType.NONE
        chroot = None
        if compressed:
            compressor = cros_build_lib.CompressionType.BZIP2
            if not cros_build_lib.IsInsideChroot():
                # TODO(b/265885353): this utility needs to either always be run
                # inside the chroot, or else this path needs to be more
                # targeted to state (Chroot.out_path) vs chroot (Chroot.path)
                # directories.
                chroot = self.chroot.path

        return cros_build_lib.CreateTarball(
            tarball_path,
            self.archive_basedir,
            compression=compressor,
            chroot=chroot,
            inputs=input_list,
            **kwargs,
        )

    def _GetTastServerFilesAndTarTransforms(self):
        """Returns Tast server files and corresponding tar transform flags.

        The returned paths should be included in AUTOTEST_SERVER_PACKAGE. The
        --transform arguments should be passed to GNU tar to convert the paths
        to appropriate destinations in the tarball.

        Returns:
            (files, transforms), where files is a list of absolute paths to Tast
            server files/directories and transforms is a list of --transform
            arguments to pass to GNU tar when archiving those files.
        """
        files = []
        transforms = []

        for path in self._GetTastSspFiles():
            if not os.path.exists(path):
                continue

            files.append(path)
            dest = os.path.join(self._TAST_SSP_SUBDIR, os.path.basename(path))
            transforms.append(
                "--transform=s|^%s|%s|" % (os.path.relpath(path, "/"), dest)
            )

        return files, transforms

    def _GetTastSspFiles(self):
        """Build out the paths to the tast SSP files.

        Returns:
            list[str] - The paths to the files.
        """
        files = []
        if cros_build_lib.IsInsideChroot():
            files.extend(self._TAST_SSP_CHROOT_FILES)
        else:
            files.extend(
                self.chroot.full_path(x) for x in self._TAST_SSP_CHROOT_FILES
            )

        for filename in self._TAST_SSP_SOURCE_FILES:
            files.append(os.path.join(constants.SOURCE_ROOT, filename))

        return files
