# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for Binhost operations."""

import os
from pathlib import Path
from unittest import mock

from chromite.api import api_config
from chromite.api.controller import binhost
from chromite.api.gen.chromite.api import binhost_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import binpkg
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.service import binhost as binhost_service


class GetBinhostsTest(cros_test_lib.MockTestCase, api_config.ApiConfigMixin):
    """Unittests for GetBinhosts."""

    def setUp(self):
        self.response = binhost_pb2.BinhostGetResponse()

    def testValidateOnly(self):
        """Check that a validate only call does not execute any logic."""
        patch = self.PatchObject(binhost_service, "GetBinhosts")

        request = binhost_pb2.BinhostGetRequest()
        request.build_target.name = "target"
        binhost.GetBinhosts(request, self.response, self.validate_only_config)
        patch.assert_not_called()

    def testMockCall(self):
        """Test a mock call does not execute logic, returns mocked value."""
        patch = self.PatchObject(binhost_service, "GetBinhosts")

        input_proto = binhost_pb2.BinhostGetRequest()
        input_proto.build_target.name = "target"

        binhost.GetBinhosts(input_proto, self.response, self.mock_call_config)

        self.assertEqual(len(self.response.binhosts), 1)
        self.assertEqual(self.response.binhosts[0].package_index, "Packages")
        patch.assert_not_called()

    def testGetBinhosts(self):
        """GetBinhosts calls service with correct args."""
        # pylint: disable=line-too-long
        binhost_list = [
            f"{constants.TRASH_BUCKET}/board/amd64-generic/paladin-R66-17.0.0-rc2/packages/",
            f"{constants.TRASH_BUCKET}/board/eve/paladin-R66-17.0.0-rc2/packages/",
        ]
        # pylint: enable=line-too-long
        get_binhost = self.PatchObject(
            binhost_service, "GetBinhosts", return_value=binhost_list
        )

        input_proto = binhost_pb2.BinhostGetRequest()
        input_proto.build_target.name = "target"

        binhost.GetBinhosts(input_proto, self.response, self.api_config)

        self.assertEqual(len(self.response.binhosts), 2)
        self.assertEqual(self.response.binhosts[0].package_index, "Packages")
        get_binhost.assert_called_once_with(mock.ANY)


class GetPrivatePrebuiltAclArgsTest(
    cros_test_lib.MockTestCase, api_config.ApiConfigMixin
):
    """Unittests for GetPrivatePrebuiltAclArgs."""

    def setUp(self):
        self.response = binhost_pb2.AclArgsResponse()

    def testValidateOnly(self):
        """Check that a validate only call does not execute any logic."""
        patch = self.PatchObject(binhost_service, "GetPrebuiltAclArgs")

        request = binhost_pb2.AclArgsRequest()
        request.build_target.name = "target"
        binhost.GetPrivatePrebuiltAclArgs(
            request, self.response, self.validate_only_config
        )
        patch.assert_not_called()

    def testMockCall(self):
        """Test a mock call does not execute logic, returns mocked value."""
        patch = self.PatchObject(binhost_service, "GetPrebuiltAclArgs")

        input_proto = binhost_pb2.AclArgsRequest()
        input_proto.build_target.name = "target"

        binhost.GetPrivatePrebuiltAclArgs(
            input_proto, self.response, self.mock_call_config
        )

        self.assertEqual(len(self.response.args), 1)
        self.assertEqual(self.response.args[0].arg, "-g")
        self.assertEqual(self.response.args[0].value, "group1:READ")
        patch.assert_not_called()

    def testGetPrivatePrebuiltAclArgs(self):
        """GetPrivatePrebuildAclsArgs calls service with correct args."""
        argvalue_list = [["-g", "group1:READ"]]
        get_binhost = self.PatchObject(
            binhost_service, "GetPrebuiltAclArgs", return_value=argvalue_list
        )

        input_proto = binhost_pb2.AclArgsRequest()
        input_proto.build_target.name = "target"

        binhost.GetPrivatePrebuiltAclArgs(
            input_proto, self.response, self.api_config
        )

        self.assertEqual(len(self.response.args), 1)
        self.assertEqual(self.response.args[0].arg, "-g")
        self.assertEqual(self.response.args[0].value, "group1:READ")
        get_binhost.assert_called_once_with(mock.ANY)


class PrepareBinhostUploadsTest(
    cros_test_lib.MockTestCase, api_config.ApiConfigMixin
):
    """Unittests for PrepareBinhostUploads."""

    def setUp(self):
        self.PatchObject(
            binhost_service,
            "GetPrebuiltsRoot",
            return_value="/build/target/packages",
        )
        self.PatchObject(
            binhost_service,
            "GetPrebuiltsFiles",
            return_value=["foo.tbz2", "bar.tbz2"],
        )
        self.PatchObject(
            binhost_service,
            "UpdatePackageIndex",
            return_value="/build/target/packages/Packages",
        )

        self.response = binhost_pb2.PrepareBinhostUploadsResponse()

    def testValidateOnly(self):
        """Check that a validate only call does not execute any logic."""
        patch = self.PatchObject(binhost_service, "GetPrebuiltsRoot")

        request = binhost_pb2.PrepareBinhostUploadsRequest()
        request.build_target.name = "target"
        request.uri = "gs://chromeos-prebuilt/target"
        rc = binhost.PrepareBinhostUploads(
            request, self.response, self.validate_only_config
        )
        patch.assert_not_called()
        self.assertEqual(rc, 0)

    def testMockCall(self):
        """Test a mock call does not execute logic, returns mocked value."""
        patch = self.PatchObject(binhost_service, "GetPrebuiltsRoot")

        request = binhost_pb2.PrepareBinhostUploadsRequest()
        request.build_target.name = "target"
        request.uri = "gs://chromeos-prebuilt/target"
        rc = binhost.PrepareBinhostUploads(
            request, self.response, self.mock_call_config
        )
        self.assertEqual(self.response.uploads_dir, "/upload/directory")
        self.assertEqual(self.response.upload_targets[0].path, "upload_target")
        patch.assert_not_called()
        self.assertEqual(rc, 0)

    def testPrepareBinhostUploads(self):
        """PrepareBinhostUploads returns Packages and tar files."""
        input_proto = binhost_pb2.PrepareBinhostUploadsRequest()
        input_proto.build_target.name = "target"
        input_proto.uri = "gs://chromeos-prebuilt/target"
        binhost.PrepareBinhostUploads(
            input_proto, self.response, self.api_config
        )
        self.assertEqual(self.response.uploads_dir, "/build/target/packages")
        self.assertCountEqual(
            [ut.path for ut in self.response.upload_targets],
            ["Packages", "foo.tbz2", "bar.tbz2"],
        )

    def testPrepareBinhostUploadsNonGsUri(self):
        """PrepareBinhostUploads dies when URI does not point to GS."""
        input_proto = binhost_pb2.PrepareBinhostUploadsRequest()
        input_proto.build_target.name = "target"
        input_proto.uri = "https://foo.bar"
        with self.assertRaises(ValueError):
            binhost.PrepareBinhostUploads(
                input_proto, self.response, self.api_config
            )


class UpdatePackageIndexTest(
    cros_test_lib.MockTempDirTestCase, api_config.ApiConfigMixin
):
    """Unit tests for BinhostService/UpdatePackageIndex."""

    def setUp(self):
        self._original_pkg_index = binpkg.PackageIndex()
        self._original_pkg_index.header["A"] = "B"
        self._original_pkg_index.packages = [
            {
                "CPV": "foo/bar",
                "KEY": "value",
            },
            {
                "CPV": "cat/pkg",
                "KEY": "also_value",
            },
        ]
        self._pkg_index_fp = os.path.join(
            self.tempdir,
            "path/to/packages/Packages",
        )

    def _write_original_package_index(self):
        """Write the package index to the tempdir.

        Note that if an input_proto specifies location=INSIDE, then they will
        not be able to find the written file, since the tempdir isn't actually
        inside a chroot.
        """
        osutils.Touch(self._pkg_index_fp, makedirs=True)
        self._original_pkg_index.WriteFile(self._pkg_index_fp)

    def testValidateOnly(self):
        """Check that a validate only call does not execute any logic."""
        self._write_original_package_index()
        patch = self.PatchObject(binpkg.PackageIndex, "ReadFilePath")
        request = binhost_pb2.UpdatePackageIndexRequest(
            package_index_file=common_pb2.Path(
                path=self._pkg_index_fp,
                location=common_pb2.Path.Location.OUTSIDE,
            ),
            set_upload_location=True,
        )
        response = binhost_pb2.UpdatePackageIndexResponse()
        binhost.UpdatePackageIndex(request, response, self.validate_only_config)
        patch.assert_not_called()

    def testMustProvideSomeCommand(self):
        """Test that an error is raised if no update types are specified."""
        self._write_original_package_index()
        request = binhost_pb2.UpdatePackageIndexRequest(
            package_index_file=common_pb2.Path(
                path=self._pkg_index_fp,
                location=common_pb2.Path.OUTSIDE,
            ),
            uri="gs://chromeos-prebuilt/board/amd64-host/packages",
        )
        response = binhost_pb2.UpdatePackageIndexResponse()
        with self.assertRaises(cros_build_lib.DieSystemExit):
            binhost.UpdatePackageIndex(request, response, self.api_config)

    def testSetUploadLocation(self):
        """Test setting the package upload location in the index file.

        This test includes correctly parsing the input uri.
        """
        # Arrange
        self._write_original_package_index()

        # Act
        request = binhost_pb2.UpdatePackageIndexRequest(
            package_index_file=common_pb2.Path(
                path=self._pkg_index_fp,
                location=common_pb2.Path.Location.OUTSIDE,
            ),
            set_upload_location=True,
            uri="gs://chromeos-prebuilt/board/amd64-host/packages/",
        )
        response = binhost_pb2.UpdatePackageIndexResponse()
        binhost.UpdatePackageIndex(request, response, self.api_config)

        # Assert
        new_pkg_index = binpkg.PackageIndex()
        new_pkg_index.ReadFilePath(self._pkg_index_fp)
        self.assertEqual(new_pkg_index.header["URI"], "gs://chromeos-prebuilt")
        self.assertDictEqual(
            new_pkg_index.packages[0],
            {
                "CPV": "cat/pkg",
                "KEY": "also_value",
                "PATH": "board/amd64-host/packages/cat/pkg.tbz2",
            },
        )
        self.assertDictEqual(
            new_pkg_index.packages[1],
            {
                "CPV": "foo/bar",
                "KEY": "value",
                "PATH": "board/amd64-host/packages/foo/bar.tbz2",
            },
        )


class SetBinhostTest(cros_test_lib.MockTestCase, api_config.ApiConfigMixin):
    """Unittests for SetBinhost."""

    def setUp(self):
        self.response = binhost_pb2.SetBinhostResponse()

    def testValidateOnly(self):
        """Check that a validate only call does not execute any logic."""
        patch = self.PatchObject(binhost_service, "SetBinhost")

        request = binhost_pb2.SetBinhostRequest()
        request.build_target.name = "target"
        request.key = binhost_pb2.POSTSUBMIT_BINHOST
        request.uri = "gs://chromeos-prebuilt/target"
        binhost.SetBinhost(request, self.response, self.validate_only_config)
        patch.assert_not_called()

    def testMockCall(self):
        """Test a mock call does not execute logic, returns mocked value."""
        patch = self.PatchObject(binhost_service, "SetBinhost")

        request = binhost_pb2.SetBinhostRequest()
        request.build_target.name = "target"
        request.key = binhost_pb2.POSTSUBMIT_BINHOST
        request.uri = "gs://chromeos-prebuilt/target"
        request.max_uris = 4
        binhost.SetBinhost(request, self.response, self.mock_call_config)
        patch.assert_not_called()
        self.assertEqual(self.response.output_file, "/path/to/BINHOST.conf")

    def testSetBinhost(self):
        """SetBinhost calls service with correct args."""
        set_binhost = self.PatchObject(
            binhost_service, "SetBinhost", return_value="/path/to/BINHOST.conf"
        )

        input_proto = binhost_pb2.SetBinhostRequest()
        input_proto.build_target.name = "target"
        input_proto.private = True
        input_proto.key = binhost_pb2.POSTSUBMIT_BINHOST
        input_proto.uri = "gs://chromeos-prebuilt/target"
        input_proto.max_uris = 4
        binhost.SetBinhost(input_proto, self.response, self.api_config)

        self.assertEqual(self.response.output_file, "/path/to/BINHOST.conf")
        set_binhost.assert_called_once_with(
            "target",
            "POSTSUBMIT_BINHOST",
            "gs://chromeos-prebuilt/target",
            private=True,
            max_uris=4,
        )


class GetBinhostConfPathTest(
    cros_test_lib.MockTestCase, api_config.ApiConfigMixin
):
    """Unittests for GetBinhostConfPath."""

    def setUp(self):
        self.response = binhost_pb2.GetBinhostConfPathResponse()

    def testValidateOnly(self):
        """Check that a validate only call does not execute any logic."""
        patch = self.PatchObject(binhost_service, "GetBinhostConfPath")

        request = binhost_pb2.GetBinhostConfPathRequest()
        request.build_target.name = "target"
        request.key = binhost_pb2.POSTSUBMIT_BINHOST
        binhost.GetBinhostConfPath(
            request, self.response, self.validate_only_config
        )
        patch.assert_not_called()

    def testMockCall(self):
        """Test a mock call does not execute logic, returns mocked value."""
        patch = self.PatchObject(binhost_service, "GetBinhostConfPath")

        request = binhost_pb2.GetBinhostConfPathRequest()
        request.build_target.name = "target"
        request.key = binhost_pb2.POSTSUBMIT_BINHOST
        binhost.GetBinhostConfPath(
            request, self.response, self.mock_call_config
        )
        patch.assert_not_called()
        self.assertEqual(self.response.conf_path, "/path/to/BINHOST.conf")

    def testGetBinhostConfPath(self):
        """GetBinhostConfPath calls service with correct args."""
        get_binhost_conf_path = self.PatchObject(
            binhost_service,
            "GetBinhostConfPath",
            return_value="/path/to/BINHOST.conf",
        )
        input_proto = binhost_pb2.GetBinhostConfPathRequest()
        input_proto.build_target.name = "target"
        input_proto.private = True
        input_proto.key = binhost_pb2.POSTSUBMIT_BINHOST
        binhost.GetBinhostConfPath(input_proto, self.response, self.api_config)

        self.assertEqual(self.response.conf_path, "/path/to/BINHOST.conf")
        get_binhost_conf_path.assert_called_once_with(
            "target",
            "POSTSUBMIT_BINHOST",
            True,
        )


class RegenBuildCacheTest(
    cros_test_lib.MockTestCase, api_config.ApiConfigMixin
):
    """Unittests for RegenBuildCache."""

    def setUp(self):
        self.response = binhost_pb2.RegenBuildCacheResponse()

    def testValidateOnly(self):
        """Check that a validate only call does not execute any logic."""
        patch = self.PatchObject(binhost_service, "RegenBuildCache")

        request = binhost_pb2.RegenBuildCacheRequest()
        request.overlay_type = binhost_pb2.OVERLAYTYPE_BOTH
        binhost.RegenBuildCache(
            request, self.response, self.validate_only_config
        )
        patch.assert_not_called()

    def testMockCall(self):
        """Test a mock call does not execute logic, returns mocked value."""
        patch = self.PatchObject(binhost_service, "RegenBuildCache")

        request = binhost_pb2.RegenBuildCacheRequest()
        request.overlay_type = binhost_pb2.OVERLAYTYPE_BOTH
        binhost.RegenBuildCache(request, self.response, self.mock_call_config)
        patch.assert_not_called()
        self.assertEqual(len(self.response.modified_overlays), 1)
        self.assertEqual(
            self.response.modified_overlays[0].path, "/path/to/BuildCache"
        )

    def testRegenBuildCache(self):
        """RegenBuildCache calls service with the correct args."""
        regen_cache = self.PatchObject(binhost_service, "RegenBuildCache")

        input_proto = binhost_pb2.RegenBuildCacheRequest()
        input_proto.overlay_type = binhost_pb2.OVERLAYTYPE_BOTH

        binhost.RegenBuildCache(input_proto, self.response, self.api_config)
        regen_cache.assert_called_once_with(mock.ANY, "both")

    def testRequiresOverlayType(self):
        """RegenBuildCache dies if overlay_type not specified."""
        regen_cache = self.PatchObject(binhost_service, "RegenBuildCache")

        input_proto = binhost_pb2.RegenBuildCacheRequest()
        input_proto.overlay_type = binhost_pb2.OVERLAYTYPE_UNSPECIFIED

        with self.assertRaises(cros_build_lib.DieSystemExit):
            binhost.RegenBuildCache(input_proto, self.response, self.api_config)
        regen_cache.assert_not_called()


class PrepareChromeBinhostUploadsTest(
    cros_test_lib.MockTempDirTestCase, api_config.ApiConfigMixin
):
    """Tests for BinhostService/PrepareChromeBinhostUploads."""

    def setUp(self):
        self.PatchObject(cros_build_lib, "IsInsideChroot", return_value=False)
        self.create_chrome_package_index_mock = self.PatchObject(
            binhost_service, "CreateChromePackageIndex"
        )

        self.chroot = chroot_lib.Chroot(
            path=self.tempdir / "chroot",
            out_path=self.tempdir / "out",
        )
        self.sysroot_path = "build/target"
        self.uploads_dir = self.tempdir / "uploads_dir"
        self.input_proto = binhost_pb2.PrepareChromeBinhostUploadsRequest()
        self.input_proto.uri = "gs://chromeos-prebuilt/target"
        self.input_proto.chroot.path = str(self.chroot.path)
        self.input_proto.chroot.out_path = str(self.chroot.out_path)
        self.input_proto.sysroot.path = self.sysroot_path
        self.input_proto.uploads_dir = str(self.uploads_dir)
        self.response = binhost_pb2.PrepareChromeBinhostUploadsResponse()

        self.packages_path = Path(
            self.chroot.full_path(self.sysroot_path, "packages")
        )
        self.chrome_packages_path = self.packages_path / constants.CHROME_CN
        osutils.Touch(
            self.chrome_packages_path / "chromeos-chrome-100-r1.tbz2",
            makedirs=True,
        )
        osutils.Touch(
            self.chrome_packages_path / "chrome-icu-100-r1.tbz2",
            makedirs=True,
        )
        osutils.Touch(
            self.chrome_packages_path / "chromeos-lacros-100-r1.tbz2",
            makedirs=True,
        )

    def testValidateOnly(self):
        """Check that a validate only call does not execute any logic."""
        binhost.PrepareChromeBinhostUploads(
            self.input_proto, self.response, self.validate_only_config
        )

        self.create_chrome_package_index_mock.assert_not_called()

    def testMockCall(self):
        """Test a mock call does not execute logic, returns mocked value."""
        binhost.PrepareChromeBinhostUploads(
            self.input_proto, self.response, self.mock_call_config
        )

        self.assertEqual(len(self.response.upload_targets), 4)
        self.assertEqual(self.response.upload_targets[3].path, "Packages")
        self.create_chrome_package_index_mock.assert_not_called()

    def testChromeUpload(self):
        """Test uploads of Chrome prebuilts."""
        expected_upload_targets = [
            "chromeos-base/chromeos-chrome-100-r1.tbz2",
            "chromeos-base/chrome-icu-100-r1.tbz2",
            "chromeos-base/chromeos-lacros-100-r1.tbz2",
        ]
        self.create_chrome_package_index_mock.return_value = (
            expected_upload_targets
        )

        binhost.PrepareChromeBinhostUploads(
            self.input_proto, self.response, self.api_config
        )

        self.assertCountEqual(
            [target.path for target in self.response.upload_targets],
            expected_upload_targets + ["Packages"],
        )

    def testPrepareBinhostUploadsNonGsUri(self):
        """PrepareBinhostUploads dies when URI does not point to GS."""
        self.input_proto.uri = "https://foo.bar"

        with self.assertRaises(ValueError):
            binhost.PrepareChromeBinhostUploads(
                self.input_proto, self.response, self.api_config
            )
