# Copyright 2016 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module that contains unittests for patch_series module."""

import contextlib
import os
from unittest import mock

from chromite.cbuildbot import patch_series
from chromite.lib import config_lib
from chromite.lib import cros_test_lib
from chromite.lib import gerrit
from chromite.lib import parallel_unittest
from chromite.lib import partial_mock
from chromite.lib import patch as cros_patch
from chromite.lib import patch_unittest


class MockManifest:
    """Helper class for Mocking Manifest objects."""

    def __init__(self, path, **kwargs):
        self.root = path
        for key, attr in kwargs.items():
            setattr(self, key, attr)


def FakeFetchChangesForRepo(fetched_changes, by_repo, repo):
    """Fake version of the "PatchSeries._FetchChangesForRepo" method.

    Thes does nothing to the changes and simply copies them into the output
    dict.
    """
    for c in by_repo[repo]:
        fetched_changes[c.id] = c


class FakePatch(partial_mock.PartialMock):
    """Mocks out dependency and fetch methods of GitRepoPatch.

    Examples:
        set FakePatch.parents and .build_roots per patch, and set
        FakePatch.assertEqual to your TestCase's assertEqual method.  The
        behavior of GerritDependencies, and Fetch` depends on the patch id.
    """

    TARGET = "chromite.lib.patch.GitRepoPatch"
    ATTRS = ("GerritDependencies", "Fetch")

    parents = {}
    build_root = None
    assertEqual = None

    def PreStart(self):
        FakePatch.parents = {}

    def PreStop(self):
        FakePatch.build_root = None
        FakePatch.assertEqual = None

    def GerritDependencies(self, patch):
        return [cros_patch.ParsePatchDep(x) for x in self.parents[patch.id]]

    def Fetch(self, patch, path):
        self._assertPath(patch, path)
        return patch.sha1

    def _assertPath(self, patch, path):
        # pylint: disable=not-callable
        self.assertEqual(path, os.path.join(self.build_root, patch.project))


class FakeGerritPatch(FakePatch):
    """Mocks out the "GerritDependencies" method of GerritPatch.

    This is necessary because GerritPatch overrides the GerritDependencies
    method.
    """

    TARGET = "chromite.lib.patch.GerritPatch"
    ATTRS = ("GerritDependencies",)


# pylint: disable=protected-access
# pylint: disable=too-many-ancestors
class PatchSeriesTestCase(
    patch_unittest.UploadedLocalPatchTestCase, cros_test_lib.MockTestCase
):
    """Base class for tests that need to test PatchSeries."""

    @contextlib.contextmanager
    def _ValidateTransactionCall(self, _changes):
        yield

    def setUp(self):
        self.StartPatcher(parallel_unittest.ParallelMock())
        self._patch_factory = patch_unittest.MockPatchFactory()
        self.build_root = "fakebuildroot"
        self.GetPatches = self._patch_factory.GetPatches
        self.MockPatch = self._patch_factory.MockPatch

    def MakeHelper(self, cros_internal=None, cros=None):
        # pylint: disable=attribute-defined-outside-init
        site_params = config_lib.GetSiteParams()
        if cros_internal:
            cros_internal = mock.create_autospec(gerrit.GerritHelper)
            cros_internal.version = "2.2"
            cros_internal.remote = site_params.INTERNAL_REMOTE
        if cros:
            cros = mock.create_autospec(gerrit.GerritHelper)
            cros.remote = site_params.EXTERNAL_REMOTE
            cros.version = "2.2"
        return patch_series.HelperPool(cros_internal=cros_internal, cros=cros)

    def GetPatchSeries(self, helper_pool=None):
        if helper_pool is None:
            helper_pool = self.MakeHelper(cros_internal=True, cros=True)
        series = patch_series.PatchSeries(self.build_root, helper_pool)

        # Suppress transactions.
        series._Transaction = self._ValidateTransactionCall
        series.GetGitRepoForChange = lambda change, **kwargs: os.path.join(
            self.build_root, change.project
        )
        series.GetGitReposForChange = lambda change, **kwargs: [
            os.path.join(self.build_root, change.project)
        ]

        return series

    def CheckPatchApply(self, apply_mocks):
        for apply_mock in apply_mocks:
            apply_mock.assert_called_once_with(mock.ANY, trivial=False)
            value = apply_mock.call_args[0][0]
            self.assertIsInstance(value, MockManifest)
            self.assertEqual(value.root, self.build_root)

    def SetPatchApply(self, patch):
        return self.PatchObject(patch, "ApplyAgainstManifest")

    def assertResults(
        self,
        series,
        changes,
        applied=(),
        failed_tot=(),
        failed_inflight=(),
        frozen=True,
    ):
        manifest = MockManifest(self.build_root)
        result = series.Apply(changes, frozen=frozen, manifest=manifest)

        _GetIds = lambda seq: [x.id for x in seq]
        _GetFailedIds = lambda seq: _GetIds(x.patch for x in seq)

        applied_result = _GetIds(result[0])
        failed_tot_result, failed_inflight_result = [
            _GetFailedIds(x) for x in result[1:]
        ]

        applied = _GetIds(applied)
        failed_tot = _GetIds(failed_tot)
        failed_inflight = _GetIds(failed_inflight)

        self.assertEqual(applied, applied_result)
        self.assertCountEqual(failed_inflight, failed_inflight_result)
        self.assertCountEqual(failed_tot, failed_tot_result)
        return result


class TestUploadedLocalPatch(PatchSeriesTestCase):
    """Test interaction between uploaded local git patches and PatchSeries."""

    def testFetchChanges(self):
        """Test fetching uploaded local patches."""
        git1, git2, patch1 = self._CommonGitSetup()
        patch2 = self.CommitFile(git1, "monkeys2", "foon2")
        patch3 = self._MkPatch(git1, None, original_sha1=patch1.sha1)
        patch4 = self._MkPatch(git1, None, original_sha1=patch2.sha1)
        self.assertEqual(patch3.id, patch1.id)
        self.assertEqual(patch4.id, patch2.id)
        self.assertNotEqual(patch3.id, patch4.id)
        series = self.GetPatchSeries()
        series.GetGitRepoForChange = lambda change, **kwargs: git2
        series.GetGitReposForChange = lambda change, **kwargs: [git2]
        patches, _ = series.FetchChanges([patch3, patch4])
        self.assertEqual(len(patches), 2)
        self.assertEqual(patches[0].id, patch3.id)
        self.assertEqual(patches[1].id, patch4.id)

    def testFetchChangesWithChangeNotInManifest(self):
        """test FetchChanges with ChangeNotInManifest."""

        # pylint: disable=unused-argument
        def raiseException(change, **kwargs):
            raise cros_patch.ChangeNotInManifest(change)

        patch_1, patch_2 = patches = self.GetPatches(2)

        series = self.GetPatchSeries()
        series.GetGitRepoForChange = raiseException
        series.GetGitReposForChange = raiseException

        changes, not_in_manifest = series.FetchChanges(patches)

        self.assertEqual(len(changes), 0)
        self.assertEqual(len(not_in_manifest), 2)
        self.assertEqual(not_in_manifest[0].patch, patch_1)
        self.assertEqual(not_in_manifest[1].patch, patch_2)
