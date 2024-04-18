# Copyright 2013 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for chromite.lib.git and helpers for testing that module."""

import datetime
import errno
import os
from pathlib import Path
import shutil
import unittest
from unittest import mock

from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import git
from chromite.lib import osutils
from chromite.lib import partial_mock


class ManifestMock(partial_mock.PartialMock):
    """Partial mock for git.Manifest."""

    TARGET = "chromite.lib.git.Manifest"
    ATTRS = ("_RunParser",)

    def _RunParser(self, *_args):
        pass


class ManifestCheckoutMock(partial_mock.PartialMock):
    """Partial mock for git.ManifestCheckout."""

    TARGET = "chromite.lib.git.ManifestCheckout"
    ATTRS = ("_GetManifestsBranch",)

    def _GetManifestsBranch(self, _root):
        return "default"


class GitWrappersTest(cros_test_lib.RunCommandTempDirTestCase):
    """Tests for small git wrappers"""

    CHANGE_ID = "I0da12ef6d2c670305f0281641bc53db22faf5c1a"
    COMMIT_LOG = (
        """
foo: Change to foo.

Change-Id: %s
"""
        % CHANGE_ID
    )

    PUSH_REMOTE = "fake_remote"
    PUSH_BRANCH = "fake_branch"
    PUSH_LOCAL = "fake_local_branch"

    def setUp(self):
        self.fake_git_dir = os.path.join(self.tempdir, "foo/bar")
        self.fake_file = "baz"
        self.fake_path = os.path.join(self.fake_git_dir, self.fake_file)

    def testInit(self):
        git.Init(self.fake_path)

        # Should have created the git repo directory, if it didn't exist.
        self.assertExists(self.fake_git_dir)
        self.assertCommandContains(["init"])

    def testClone(self):
        url = "http://happy/git/repo"

        git.Clone(self.fake_git_dir, url)

        # Should have created the git repo directory, if it didn't exist.
        self.assertExists(self.fake_git_dir)
        self.assertCommandContains(["git", "clone", url, self.fake_git_dir])

    def testCloneComplex(self):
        url = "http://happy/git/repo"
        ref = "other/git/repo"

        git.Clone(
            self.fake_git_dir,
            url,
            reference=ref,
            branch="feature",
            single_branch=True,
        )

        self.assertCommandContains(
            [
                "git",
                "clone",
                url,
                self.fake_git_dir,
                "--reference",
                ref,
                "--branch",
                "feature",
                "--single-branch",
            ]
        )

    def testShallowFetchDefault(self):
        url = "http://happy/git/repo"

        git.ShallowFetch(self.fake_git_dir, url)

        # Should have created the git repo directory, if it didn't exist.
        self.assertExists(self.fake_git_dir)
        self.assertCommandContains(["init"])
        self.assertCommandContains(["remote", "add", "origin", url])
        self.assertCommandContains(["fetch", "--depth=1"])
        self.assertCommandContains(["pull", "origin", "HEAD"])

        sparse_checkout = os.path.join(
            self.fake_git_dir, ".git", "info", "sparse-checkout"
        )
        self.assertNotExists(sparse_checkout)

    def testShallowFetchCommit(self):
        url = "http://happy/git/repo"

        git.ShallowFetch(
            self.fake_git_dir,
            url,
            commit="1234",
        )

        # Should have created the git repo directory, if it didn't exist.
        self.assertExists(self.fake_git_dir)
        self.assertCommandContains(["init"])
        self.assertCommandContains(["remote", "add", "origin", url])
        self.assertCommandContains(["fetch", "--depth=1", "origin", "1234"])
        self.assertCommandContains(["pull", "origin", "HEAD"])

        sparse_checkout = os.path.join(
            self.fake_git_dir, ".git", "info", "sparse-checkout"
        )
        self.assertNotExists(sparse_checkout)

    def testShallowFetchSparseCheckout(self):
        url = "http://happy/git/repo"

        sparse_checkout = os.path.join(
            self.fake_git_dir, ".git", "info", "sparse-checkout"
        )
        osutils.SafeMakedirs(os.path.dirname(sparse_checkout))

        git.ShallowFetch(
            self.fake_git_dir, url, sparse_checkout=["dir1/file1", "dir2/file2"]
        )

        # Should have created the git repo directory, if it didn't exist.
        self.assertExists(self.fake_git_dir)
        self.assertCommandContains(["init"])
        self.assertCommandContains(["config", "core.sparsecheckout", "true"])
        self.assertCommandContains(["remote", "add", "origin", url])
        self.assertCommandContains(["fetch", "--depth=1"])
        self.assertCommandContains(["pull", "origin", "HEAD"])
        self.assertEqual(
            osutils.ReadFile(sparse_checkout), "dir1/file1\ndir2/file2"
        )

    def testFindGitTopLevel(self):
        git.FindGitTopLevel(self.fake_path)
        self.assertCommandContains(["--show-toplevel"])

    def testGetCurrentBranchOrId_NoBranch(self):
        test_hash = "5" * 40
        self.rc.AddCmdResult(partial_mock.In("symbolic-ref"), returncode=1)
        self.rc.AddCmdResult(
            partial_mock.In("rev-parse"), stdout="%s\n" % test_hash
        )
        self.assertEqual(git.GetCurrentBranchOrId(self.fake_path), test_hash)
        self.assertCommandContains(["rev-parse", "HEAD"])

    def testGetCurrentBranchOrId_OnBranch(self):
        self.rc.AddCmdResult(
            partial_mock.In("symbolic-ref"), stdout="refs/heads/branch\n"
        )
        self.assertEqual(git.GetCurrentBranchOrId(self.fake_path), "branch")
        self.assertCommandContains(["symbolic-ref", "-q", "HEAD"])

    def testLsFiles(self):
        files = [".", "somefile.txt"]
        git.LsFiles(cwd=self.fake_path, files=files)
        self.assertCommandContains(["ls-files", "-z"])
        self.assertCommandContains(["--exclude-standard"])
        self.assertCommandContains(["--cached"])
        self.assertCommandContains(["--", *files])

    def testLsTree(self):
        files = ["exec.sh", "file.txt", "sym"]
        # pylint: disable=line-too-long
        self.rc.AddCmdResult(
            partial_mock.In("ls-tree"),
            stdout=(
                "100755 blob 6a80f36980ec5de2357b7316a57559152af409fd\texec.sh\0"
                "100644 blob 5c7d9bdc60697775b63c8b04de64cc67f4eeba5c\tfile.txt\0"
                "120000 blob 702f5b64cc06d3ccc44e840c1e0714c043978c83\tsym\0"
            ),
        )
        # pylint: enable=line-too-long
        ret = git.LsTree(cwd=self.fake_path, commit="HEAD", files=files)
        self.assertCommandContains(["ls-tree", "-r", "-z"])
        self.assertCommandContains(["--", "HEAD", "--"])
        self.assertCommandContains(["--", *files])
        self.assertEqual(
            ret,
            [
                git.LsTreeEntry(
                    name=Path("exec.sh"),
                    is_exec=True,
                    is_file=True,
                    is_symlink=False,
                ),
                git.LsTreeEntry(
                    name=Path("file.txt"),
                    is_exec=False,
                    is_file=True,
                    is_symlink=False,
                ),
                git.LsTreeEntry(
                    name=Path("sym"),
                    is_exec=False,
                    is_file=False,
                    is_symlink=True,
                ),
            ],
        )

    def testLsTreeEmptyFileList(self):
        """Tests git.LsTree with the `files` argument being empty."""
        git.LsTree(cwd=self.fake_path, commit="HEAD")
        self.assertCommandContains(["ls-tree", "-r", "-z"])
        self.assertCommandContains(["--", "HEAD"])
        self.assertCommandContains(["HEAD", "--"], expected=False)

    def testAddPath(self):
        git.AddPath(self.fake_path)
        self.assertCommandContains(["add"])
        self.assertCommandContains([self.fake_file])

    def testRmPath(self):
        git.RmPath(self.fake_path)
        self.assertCommandContains(["rm"])
        self.assertCommandContains([self.fake_file])

    def testGetObjectAtRev(self):
        git.GetObjectAtRev(self.fake_git_dir, ".", "1234")
        self.assertCommandContains(["show"])

    def testRevertPath(self):
        git.RevertPath(self.fake_git_dir, self.fake_file, "1234")
        self.assertCommandContains(["checkout"])
        self.assertCommandContains([self.fake_file])

    def testCommit(self):
        self.rc.AddCmdResult(partial_mock.In("log"), stdout=self.COMMIT_LOG)
        git.Commit(self.fake_git_dir, "bar")
        self.assertCommandContains(["--amend"], expected=False)
        cid = git.Commit(self.fake_git_dir, "bar", amend=True)
        self.assertCommandContains(["--amend"])
        self.assertCommandContains(["--allow-empty"], expected=False)
        self.assertEqual(cid, self.CHANGE_ID)
        cid = git.Commit(self.fake_git_dir, "new", allow_empty=True)
        self.assertCommandContains(["--allow-empty"])

    def testUploadCLNormal(self):
        git.UploadCL(
            self.fake_git_dir,
            self.PUSH_REMOTE,
            self.PUSH_BRANCH,
            local_branch=self.PUSH_LOCAL,
        )
        self.assertCommandContains(
            ["%s:refs/for/%s" % (self.PUSH_LOCAL, self.PUSH_BRANCH)],
            stdout=None,
        )

    def testUploadCLDraft(self):
        git.UploadCL(
            self.fake_git_dir,
            self.PUSH_REMOTE,
            self.PUSH_BRANCH,
            local_branch=self.PUSH_LOCAL,
            draft=True,
        )
        self.assertCommandContains(
            ["%s:refs/drafts/%s" % (self.PUSH_LOCAL, self.PUSH_BRANCH)],
            stdout=None,
        )

    def testUploadCLCaptured(self):
        git.UploadCL(
            self.fake_git_dir,
            self.PUSH_REMOTE,
            self.PUSH_BRANCH,
            local_branch=self.PUSH_LOCAL,
            draft=True,
            capture_output=True,
        )
        self.assertCommandContains(
            ["%s:refs/drafts/%s" % (self.PUSH_LOCAL, self.PUSH_BRANCH)],
            capture_output=True,
        )

    def testGetGitRepoRevision(self):
        git.GetGitRepoRevision(self.fake_git_dir)
        self.assertCommandContains(["rev-parse", "HEAD"])
        git.GetGitRepoRevision(self.fake_git_dir, branch="branch")
        self.assertCommandContains(["rev-parse", "branch"])
        git.GetGitRepoRevision(self.fake_git_dir, short=True)
        self.assertCommandContains(["rev-parse", "--short", "HEAD"])
        git.GetGitRepoRevision(self.fake_git_dir, branch="branch", short=True)
        self.assertCommandContains(["rev-parse", "--short", "branch"])

    def testGetGitGitdir(self):
        git.Init(self.fake_git_dir)
        os.makedirs(os.path.join(self.fake_git_dir, ".git", "refs", "heads"))
        os.makedirs(os.path.join(self.fake_git_dir, ".git", "objects"))
        other_file = os.path.join(self.fake_git_dir, "other_file")
        osutils.Touch(other_file)

        ret = git.GetGitGitdir(self.fake_git_dir)
        self.assertEqual(ret, os.path.join(self.fake_git_dir, ".git"))

    def testGetGitGitdir_bare(self):
        git.Init(self.fake_git_dir)
        os.makedirs(os.path.join(self.fake_git_dir, "refs", "heads"))
        os.makedirs(os.path.join(self.fake_git_dir, "objects"))
        config_file = os.path.join(self.fake_git_dir, "config")
        osutils.Touch(config_file)

        ret = git.GetGitGitdir(self.fake_git_dir)
        self.assertEqual(ret, self.fake_git_dir)

    def testGetGitGitdir_worktree(self):
        dotgit = os.path.join(self.tempdir, ".git")
        osutils.WriteFile(dotgit, "gitdir: /foo")
        ret = git.GetGitGitdir(self.tempdir)
        self.assertEqual(ret, dotgit)

    def testGetGitGitdir_negative(self):
        ret = git.GetGitGitdir(self.tempdir)
        self.assertFalse(ret)

    def testDeleteStaleLocks(self):
        git.Init(self.fake_git_dir)
        refs_heads = os.path.join(self.fake_git_dir, ".git", "refs", "heads")
        os.makedirs(refs_heads)
        objects = os.path.join(self.fake_git_dir, ".git", "objects")
        os.makedirs(objects)
        fake_lock = os.path.join(refs_heads, "main.lock")
        osutils.Touch(fake_lock)
        os.makedirs(self.fake_path)
        dot_lock_not_in_dot_git = os.path.join(self.fake_git_dir, "some.lock")
        osutils.Touch(dot_lock_not_in_dot_git)
        other_file = os.path.join(self.fake_path, "other_file")
        osutils.Touch(other_file)

        git.DeleteStaleLocks(self.fake_git_dir)
        self.assertExists(os.path.join(self.fake_git_dir, ".git"))
        self.assertExists(refs_heads)
        self.assertExists(objects)
        self.assertExists(dot_lock_not_in_dot_git)
        self.assertExists(other_file)
        self.assertNotExists(fake_lock)

    def testDeleteStaleLocks_bare(self):
        git.Init(self.fake_git_dir)
        refs_heads = os.path.join(self.fake_git_dir, "refs", "heads")
        os.makedirs(refs_heads)
        objects = os.path.join(self.fake_git_dir, "objects")
        os.makedirs(objects)
        fake_lock = os.path.join(refs_heads, "main.lock")
        osutils.Touch(fake_lock)
        os.makedirs(self.fake_path)
        other_file = os.path.join(self.fake_path, "other_file")
        osutils.Touch(other_file)

        git.DeleteStaleLocks(self.fake_git_dir)
        self.assertExists(refs_heads)
        self.assertExists(objects)
        self.assertExists(other_file)
        self.assertNotExists(fake_lock)

    def testGetUrlFromRemoteOutput(self):
        """Test that the proper URL is returned from the git remote output."""
        remote_output = (
            "remote:\nremote:\nremote:   "
            "https://example.com/c/some/project/repo/+/123 gerrit: test"
        )
        url = git.GetUrlFromRemoteOutput(remote_output)
        self.assertEqual(url, "https://example.com/c/some/project/repo/+/123")

        remote_output = (
            "remote:\nremote:\nremote:   "
            "https://chrome-internal-review.googlesource.com/c/chromeos/"
            "manifest-internal/+/4298120 LTS: update kernel commit_ids for LTS "
            "branches [NEW]  "
        )
        url = git.GetUrlFromRemoteOutput(remote_output)
        self.assertEqual(
            url,
            "https://chrome-internal-review.googlesource.com/c/chromeos/"
            "manifest-internal/+/4298120",
        )

        remote_output = (
            "remote:\nremote:\nremote:   "
            "c/some/project/repo/+/123 gerrit: test"
        )
        url = git.GetUrlFromRemoteOutput(remote_output)
        self.assertIsNone(url)


class LogTest(cros_test_lib.RunCommandTestCase):
    """Tests for git.Log"""

    def testNoArgs(self):
        git.Log("git/repo/path")
        self.assertCommandContains(["git", "log"], cwd="git/repo/path")

    def testAllArgs(self):
        git.Log(
            "git/repo/path",
            format='format:"%cd"',
            after="1996-01-01",
            until="1997-01-01",
            reverse=True,
            date="unix",
            max_count="1",
            grep="^Change-ID: I9f701664d849197cf183fc1fb46f7523095c359c$",
            rev="m/main",
            paths=["my/path"],
        )
        self.assertCommandContains(
            [
                "git",
                "log",
                '--format=format:"%cd"',
                "--after=1996-01-01",
                "--until=1997-01-01",
                "--reverse",
                "--date=unix",
                "--max-count=1",
                "--grep=^Change-ID: I9f701664d849197cf183fc1fb46f7523095c359c$",
                "m/main",
                "--",
                "my/path",
            ],
            cwd="git/repo/path",
        )


class ChangeIdTest(cros_test_lib.MockTestCase):
    """Tests for git.GetChangeId function."""

    def testHEAD(self):
        """Test the parsing of the git.GetChangeId function for HEAD."""

        log_output = """
lib/git: break out ChangeId into its own function

Code in Commit() will get the Change-Id after doing a git commit,
but in some use cases, we want to get the Change-Id of a commit
that already exists, without changing it. Move this code into its
own function that Commit() calls or an external user can call it
directly.

BUG=None
TEST=Start python3
>>> from chromite.lib import git
>>> print(git.GetChangeId('.'))
>>> exit(0)
$ git show
Compare the Change-Id printed by the python code with that shown

Change-Id: Ia7b712c42ff83c52c0fb5d88d1ef6c62f49da88d
"""
        result = cros_build_lib.CompletedProcess(stdout=log_output)
        self.PatchObject(git, "RunGit", return_value=result)

        changeid = git.GetChangeId("git/repo/path")
        self.assertEqual(changeid, "Ia7b712c42ff83c52c0fb5d88d1ef6c62f49da88d")

    def testSpecificSHA(self):
        """Test the parsing of git.GetChangeId function for a specific SHA."""

        sha = "235511fbd7158c6d02c070944eb59cf47b37fcb5"
        log_output = """
Add user cros-disks to group android-everybody

This allows cros-disks to access 'Play Files'.

BUG=chromium:996549
TEST=Manually built and inspected group file

Cq-Depend: chromium:2032906
Change-Id: Id31c1211f95d7f5c3a94fbe8c028f65d3509f363
Reviewed-on: https://chromium-review.googlesource.com/c/chromiumos/chromite/+/2040633
Reviewed-by: Mike Frysinger <vapier@chromium.org>
Commit-Queue: François Degros <fdegros@chromium.org>
Tested-by: François Degros <fdegros@chromium.org>
"""
        result = cros_build_lib.CompletedProcess(stdout=log_output)
        self.PatchObject(git, "RunGit", return_value=result)

        changeid = git.GetChangeId("git/repo/path", sha)
        self.assertEqual(changeid, "Id31c1211f95d7f5c3a94fbe8c028f65d3509f363")

    def testNoChangeId(self):
        """Test git.GetChangeId function if there is no Change-Id."""

        log_output = """
lib/git: break out ChangeId into its own function

Code in Commit() will get the Change-Id after doing a git commit,
but in some use cases, we want to get the Change-Id of a commit
that already exists, without changing it. Move this code into its
own function that Commit() calls or an external user can call it
directly.

BUG=None
TEST=Start python3
>>> from chromite.lib import git
>>> print(git.GetChangeId('.'))
>>> exit(0)
$ git show
Compare the Change-Id printed by the python code with that shown
"""
        result = cros_build_lib.CompletedProcess(stdout=log_output)
        self.PatchObject(git, "RunGit", return_value=result)

        changeid = git.GetChangeId("git/repo/path")
        self.assertIsNone(changeid)

    def testChangeIdInTextCol1(self):
        """Test git.GetChangeId when 'Change-Id' is in the text."""

        log_output = """
new_variant: track branch name and change-id

new_variant.py calls several scripts to create a new variant of a
reference board. Each of these scripts adds or modifies files and
creates a new commit. Track the branch name and change-id of each
commit in preparation for uploading to gerrit.
This CL builds on the changes in
Change-Id: I53af157625257ee1ecf39a4ced979138890b54f1
and while I would normally use a relation chain or cq-depend, I'm
putting the text directly in here so that the unit test will fail
until I fix the code to handle the pathological cases.

Cq-Depend: chromium:2041804
Change-Id: Ib71696f76dc80f1a76b8e7a73493c6c2668e2c6f
"""
        result = cros_build_lib.CompletedProcess(stdout=log_output)
        self.PatchObject(git, "RunGit", return_value=result)

        self.assertRaises(ValueError, git.GetChangeId, "git/repo/path")

    def testChangeIdInTextNotCol1(self):
        """Test git.GetChangeId when 'Change-Id' is in the text."""

        log_output = """
new_variant: track branch name and change-id

new_variant.py calls several scripts to create a new variant of a
reference board. Each of these scripts adds or modifies files and
creates a new commit. Track the branch name and change-id of each
commit in preparation for uploading to gerrit. This CL builds on the
changes in Change-Id: I53af157625257ee1ecf39a4ced979138890b54f1
and while I would normally use a relation chain or cq-depend, I'm
putting the text directly in here so that the unit test will fail
until I fix the code to handle the pathological cases.

Cq-Depend: chromium:2041804
Change-Id: Ib71696f76dc80f1a76b8e7a73493c6c2668e2c6f
"""
        result = cros_build_lib.CompletedProcess(stdout=log_output)
        self.PatchObject(git, "RunGit", return_value=result)

        changeid = git.GetChangeId("git/repo/path")
        self.assertEqual(changeid, "Ib71696f76dc80f1a76b8e7a73493c6c2668e2c6f")


class ProjectCheckoutTest(cros_test_lib.TestCase):
    """Tests for git.ProjectCheckout"""

    def setUp(self):
        self.fake_unversioned_patchable = git.ProjectCheckout(
            dict(
                name="chromite",
                path="src/chromite",
                revision="remotes/for/main",
            )
        )
        self.fake_unversioned_unpatchable = git.ProjectCheckout(
            dict(
                name="chromite",
                path="src/platform/somethingsomething/chromite",
                # Pinned to a SHA1.
                revision="1deadbeeaf1deadbeeaf1deadbeeaf1deadbeeaf",
            )
        )
        self.fake_versioned_patchable = git.ProjectCheckout(
            dict(
                name="chromite",
                path="src/chromite",
                revision="1deadbeeaf1deadbeeaf1deadbeeaf1deadbeeaf",
                upstream="remotes/for/main",
            )
        )
        self.fake_versioned_unpatchable = git.ProjectCheckout(
            dict(
                name="chromite",
                path="src/chromite",
                revision="1deadbeeaf1deadbeeaf1deadbeeaf1deadbeeaf",
                upstream="1deadbeeaf1deadbeeaf1deadbeeaf1deadbeeaf",
            )
        )


class RawDiffTest(cros_test_lib.MockTestCase):
    """Tests for git.RawDiff function."""

    def testRawDiff(self):
        """Test the parsing of the git.RawDiff function."""
        # pylint: disable=line-too-long
        diff_output = """
:100644 100644 ac234b2... 077d1f8... M\tchromeos-base/chromeos-chrome/Manifest
:100644 100644 9e5d11b... 806bf9b... R099\tchromeos-base/chromeos-chrome/chromeos-chrome-40.0.2197.0_rc-r1.ebuild\tchromeos-base/chromeos-chrome/chromeos-chrome-40.0.2197.2_rc-r1.ebuild
:100644 100644 70d6e94... 821c642... M\tchromeos-base/chromeos-chrome/chromeos-chrome-9999.ebuild
:100644 100644 be445f9... be445f9... R100\tchromeos-base/chromium-source/chromium-source-40.0.2197.0_rc-r1.ebuild\tchromeos-base/chromium-source/chromium-source-40.0.2197.2_rc-r1.ebuild
:100644 100644 d02943a... 114bc47... M\tchromeos-base/chromeos-chrome/User Data.txt
"""
        # pylint: enable=line-too-long
        result = cros_build_lib.CompletedProcess(stdout=diff_output)
        self.PatchObject(git, "RunGit", return_value=result)

        entries = git.RawDiff("foo", "bar")
        self.assertEqual(
            entries,
            [
                (
                    "100644",
                    "100644",
                    "ac234b2",
                    "077d1f8",
                    "M",
                    None,
                    "chromeos-base/chromeos-chrome/Manifest",
                    None,
                    [],
                    [],
                ),
                (
                    "100644",
                    "100644",
                    "9e5d11b",
                    "806bf9b",
                    "R",
                    "099",
                    "chromeos-base/chromeos-chrome/"
                    "chromeos-chrome-40.0.2197.0_rc-r1.ebuild",
                    "chromeos-base/chromeos-chrome/"
                    "chromeos-chrome-40.0.2197.2_rc-r1.ebuild",
                    [],
                    [],
                ),
                (
                    "100644",
                    "100644",
                    "70d6e94",
                    "821c642",
                    "M",
                    None,
                    "chromeos-base/chromeos-chrome/chromeos-chrome-9999.ebuild",
                    None,
                    [],
                    [],
                ),
                (
                    "100644",
                    "100644",
                    "be445f9",
                    "be445f9",
                    "R",
                    "100",
                    "chromeos-base/chromium-source/"
                    "chromium-source-40.0.2197.0_rc-r1.ebuild",
                    "chromeos-base/chromium-source/"
                    "chromium-source-40.0.2197.2_rc-r1.ebuild",
                    [],
                    [],
                ),
                (
                    "100644",
                    "100644",
                    "d02943a",
                    "114bc47",
                    "M",
                    None,
                    "chromeos-base/chromeos-chrome/User Data.txt",
                    None,
                    [],
                    [],
                ),
            ],
        )

    def testEmptyDiff(self):
        """Verify an empty diff doesn't crash."""
        result = cros_build_lib.CompletedProcess(stdout="\n")
        self.PatchObject(git, "RunGit", return_value=result)
        entries = git.RawDiff("foo", "bar")
        self.assertEqual([], entries)

    def testMergeDiff(self):
        """Verify a merge diff."""

        diff_output = """
::100644 100644 100644 fabadb8 cc95eb0 4866510 MM\tdesc.c
::100755 100755 100755 52b7a2d 6d1ac04 d2ac7d7 RM\tfoo.sh
::100644 100644 100644 e07d6c5 9042e82 ee91881 RR\tfooey.c
::100644 100644 100644 c238559 e0512aa 3814dac MM\tUser Data.txt
"""
        result = cros_build_lib.CompletedProcess(stdout=diff_output)
        self.PatchObject(git, "RunGit", return_value=result)

        entries = git.RawDiff("foo", "bar")
        self.assertEqual(
            entries,
            [
                (
                    "100644",
                    "100644",
                    "fabadb8",
                    "4866510",
                    "MM",
                    None,
                    None,
                    "desc.c",
                    ["100644"],
                    ["cc95eb0"],
                ),
                (
                    "100755",
                    "100755",
                    "52b7a2d",
                    "d2ac7d7",
                    "RM",
                    None,
                    None,
                    "foo.sh",
                    ["100755"],
                    ["6d1ac04"],
                ),
                (
                    "100644",
                    "100644",
                    "e07d6c5",
                    "ee91881",
                    "RR",
                    None,
                    None,
                    "fooey.c",
                    ["100644"],
                    ["9042e82"],
                ),
                (
                    "100644",
                    "100644",
                    "c238559",
                    "3814dac",
                    "MM",
                    None,
                    None,
                    "User Data.txt",
                    ["100644"],
                    ["e0512aa"],
                ),
            ],
        )

    def testMultipleMergeDiff(self):
        """Verify a merge with more than 2 parents."""
        diff_output = (
            ":::::100644 100644 100644 100644 100644 100644"
            " 074918267e36d09b990c69066f7dd21f7c7b4d55"
            " 8514c07df3081c4b26144f92b0adc58b543dff55"
            " ceedecec86cacf5687470d8543d0cfc9456df473"
            " 7bb53f20d7fa362a5336924cdee739e0c0ffdb2c"
            " 4b6c09ad33e6b255d86b8f7606075fbaa1be5c41"
            " 6a216f484aaccc3a022ce3d4712f86f24265600d"
            " MMMMM\tfile"
        )
        result = cros_build_lib.CompletedProcess(stdout=diff_output)
        self.PatchObject(git, "RunGit", return_value=result)

        entries = git.RawDiff("foo", "bar")
        self.assertEqual(
            entries,
            [
                (
                    "100644",
                    "100644",
                    "074918267e36d09b990c69066f7dd21f7c7b4d55",
                    "6a216f484aaccc3a022ce3d4712f86f24265600d",
                    "MMMMM",
                    None,
                    None,
                    "file",
                    ["100644", "100644", "100644", "100644"],
                    [
                        "8514c07df3081c4b26144f92b0adc58b543dff55",
                        "ceedecec86cacf5687470d8543d0cfc9456df473",
                        "7bb53f20d7fa362a5336924cdee739e0c0ffdb2c",
                        "4b6c09ad33e6b255d86b8f7606075fbaa1be5c41",
                    ],
                ),
            ],
        )


class GitPushTest(cros_test_lib.RunCommandTestCase):
    """Tests for git.GitPush function."""

    # Non fast-forward push error message.
    NON_FF_PUSH_ERROR = (
        "To https://localhost/repo.git\n"
        "! [remote rejected] main -> main (non-fast-forward)\n"
        "error: failed to push some refs to 'https://localhost/repo.git'\n"
    )

    # List of possible GoB transient errors.
    TRANSIENT_ERRORS = (
        # Hook error when creating a new branch from SHA1 ref.
        (
            "remote: Processing changes: (-)To https://localhost/repo.git\n"
            "! [remote rejected] 6c78ca083c3a9d64068c945fd9998eb1e0a3e739 -> "
            "stabilize-4636.B (error in hook)\n"
            "error: failed to push some refs to 'https://localhost/repo.git'\n"
        ),
        # 'failed to lock' error when creating a new branch from SHA1 ref.
        (
            "remote: Processing changes: done\nTo https://localhost/repo.git\n"
            "! [remote rejected] 4ea09c129b5fedb261bae2431ce2511e35ac3923 -> "
            "stabilize-daisy-4319.96.B (failed to lock)\n"
            "error: failed to push some refs to 'https://localhost/repo.git'\n"
        ),
        # Hook error when pushing branch.
        (
            "remote: Processing changes: (\\)To https://localhost/repo.git\n"
            "! [remote rejected] temp_auto_checkin_branch -> "
            "main (error in hook)\n"
            "error: failed to push some refs to 'https://localhost/repo.git'\n"
        ),
        # Another kind of error when pushing a branch.
        "fatal: remote error: Internal Server Error",
        # crbug.com/298189
        (
            "error: gnutls_handshake() failed: A TLS packet with unexpected "
            "length was received. while accessing "
            "http://localhost/repo.git/info/refs?service=git-upload-pack\n"
            "fatal: HTTP request failed"
        ),
        # crbug.com/298189
        (
            "fatal: unable to access 'https://localhost/repo.git': GnuTLS recv "
            "error (-9): A TLS packet with unexpected length was received."
        ),
    )

    def setUp(self):
        self.StartPatcher(mock.patch("time.sleep"))

    @staticmethod
    def _RunGitPush():
        """Runs git.GitPush with some default arguments."""
        git.GitPush(
            "some_repo_path",
            "local-ref",
            git.RemoteRef("some-remote", "remote-ref"),
        )

    def testGitPushSimple(self):
        """Test GitPush with minimal arguments."""
        git.GitPush("git_path", "HEAD", git.RemoteRef("origin", "main"))
        self.assertCommandCalled(
            ["git", "push", "origin", "HEAD:main"],
            print_cmd=False,
            stdout=True,
            stderr=True,
            cwd="git_path",
            encoding="utf-8",
        )

    def testGitPushComplex(self):
        """Test GitPush with some arguments."""
        git.GitPush(
            "git_path",
            "HEAD",
            git.RemoteRef("origin", "main"),
            force=True,
            dry_run=True,
        )
        self.assertCommandCalled(
            ["git", "push", "origin", "HEAD:main", "--force", "--dry-run"],
            print_cmd=False,
            stdout=True,
            stderr=True,
            cwd="git_path",
            encoding="utf-8",
        )

    def testNonFFPush(self):
        """Non fast-forward push error propagates to the caller."""
        self.rc.AddCmdResult(
            partial_mock.In("push"),
            returncode=128,
            stderr=self.NON_FF_PUSH_ERROR,
        )
        self.assertRaises(cros_build_lib.RunCommandError, self._RunGitPush)

    def testPersistentTransientError(self):
        """GitPush fails if transient error occurs multiple times."""
        for error in self.TRANSIENT_ERRORS:
            self.rc.AddCmdResult(
                partial_mock.In("push"), returncode=128, stderr=error
            )
            self.assertRaises(cros_build_lib.RunCommandError, self._RunGitPush)


class GitIntegrationTest(cros_test_lib.TempDirTestCase):
    """Tests that git library functions work with actual git repos."""

    def setUp(self):
        self.source = os.path.join(self.tempdir, "src")
        git.Init(self.source)
        # Nerf any hooks the OS might have installed on us as they aren't going
        # to be useful to us, just slow things down.
        shutil.rmtree(os.path.join(self.source, ".git", "hooks"))
        cros_build_lib.run(
            ["git", "commit", "--allow-empty", "-m", "initial commit"],
            cwd=self.source,
            print_cmd=False,
            capture_output=True,
        )

    def _CommitFile(self, repo, filename, content):
        osutils.WriteFile(os.path.join(repo, filename), content)
        git.AddPath(os.path.join(repo, filename))
        git.Commit(repo, "commit %s" % (cros_build_lib.GetRandomString(),))
        return git.GetGitRepoRevision(repo)

    def testIsReachable(self):
        sha1 = self._CommitFile(self.source, "foo", "foo")
        sha2 = self._CommitFile(self.source, "bar", "bar")
        self.assertTrue(git.IsReachable(self.source, sha1, sha2))
        self.assertFalse(git.IsReachable(self.source, sha2, sha1))

    def testDoesCommitExistInRepoWithAmbiguousBranchName(self):
        git.CreateBranch(self.source, "peach", track=True)
        self._CommitFile(self.source, "peach", "Keep me.")
        self.assertTrue(git.DoesCommitExistInRepo(self.source, "peach"))


class ManifestCheckoutTest(cros_test_lib.TempDirTestCase):
    """Tests for ManifestCheckout functionality."""

    def setUp(self):
        self.manifest_dir = os.path.join(self.tempdir, ".repo", "manifests")

        # Initialize a repo instance here.
        local_repo = os.path.join(constants.SOURCE_ROOT, ".repo/repo/.git")

        # TODO(evanhernandez): This is a hack. Find a way to simplify this test.
        # We used to use the current checkout's manifests.git, but that caused
        # problems in production environments.
        remote_manifests = os.path.join(self.tempdir, "remote", "manifests.git")
        osutils.SafeMakedirs(remote_manifests)
        git.Init(remote_manifests)
        default_manifest = os.path.join(remote_manifests, "default.xml")
        osutils.WriteFile(
            default_manifest,
            '<?xml version="1.0" encoding="UTF-8"?><manifest></manifest>',
        )
        git.AddPath(default_manifest)
        git.Commit(remote_manifests, "stub commit", allow_empty=True)
        git.CreateBranch(remote_manifests, "default")
        git.CreateBranch(remote_manifests, "release-R23-2913.B")
        git.CreateBranch(remote_manifests, "release-R23-2913.B-suffix")
        git.CreateBranch(remote_manifests, "firmware-link-")
        # This must come last as it sets up HEAD for the default branch, and
        # repo uses that to figure out which branch to check out.
        git.CreateBranch(remote_manifests, "master")

        # Create a copy of our existing manifests.git, but rewrite it so it
        # looks like a remote manifests.git.  This is to avoid hitting the
        # network, and speeds things up in general.
        local_manifests = "file://%s" % remote_manifests
        temp_manifests = os.path.join(self.tempdir, "manifests.git")
        git.RunGit(self.tempdir, ["clone", "-n", "--bare", local_manifests])
        git.RunGit(
            temp_manifests,
            [
                "fetch",
                "-f",
                "-u",
                local_manifests,
                "refs/remotes/origin/*:refs/heads/*",
            ],
        )
        git.RunGit(temp_manifests, ["branch", "-D", "default"])
        cmd = [
            "repo",
            "init",
            "-u",
            temp_manifests,
            "--no-current-branch",
            "--repo-branch",
            "default",
            "--repo-url",
            "file://%s" % local_repo,
        ]
        # TODO(vapier): Drop conditional check once we've fully rolled to newer
        # repo and can assume this exists.
        result = cros_build_lib.run(
            ["repo", "init", "--help"], capture_output=True, cwd=self.tempdir
        )
        if b"--manifest-depth" in result.stdout:
            cmd += ["--manifest-depth=0"]
        cros_build_lib.run(cmd, cwd=self.tempdir)

        self.active_manifest = os.path.realpath(
            os.path.join(self.tempdir, ".repo", "manifest.xml")
        )

    # TODO(b/245813531): Re-enable when repo v2.29 is stable.
    @unittest.skip("Skip until staging and prod are on repo v2.29 b/245333797")
    def testManifestInheritance(self):
        osutils.WriteFile(
            self.active_manifest,
            """
        <manifest>
          <include name="include-target.xml" />
          <include name="empty.xml" />
          <project name="monkeys" path="baz" remote="foon" revision="main" />
        </manifest>""",
        )
        # First, verify it properly explodes if the include can't be found.
        self.assertRaises(EnvironmentError, git.ManifestCheckout, self.tempdir)

        # Next, verify it can read an empty manifest; this is to ensure
        # that we can point Manifest at the empty manifest without exploding,
        # same for ManifestCheckout; this sort of thing is primarily useful
        # to ensure no step of an include assumes everything is yet assembled.
        empty_path = os.path.join(self.manifest_dir, "empty.xml")
        osutils.WriteFile(empty_path, "<manifest/>")
        git.Manifest(empty_path)
        git.ManifestCheckout(self.tempdir, manifest_path=empty_path)

        # Next, verify include works.
        osutils.WriteFile(
            os.path.join(self.manifest_dir, "include-target.xml"),
            """
        <manifest>
          <remote name="foon" fetch="http://localhost" />
        </manifest>""",
        )
        manifest = git.ManifestCheckout(self.tempdir)
        self.assertEqual(list(manifest.checkouts_by_name), ["monkeys"])
        self.assertEqual(list(manifest.remotes), ["foon"])

    # TODO(b/245813531): Re-enable when repo v2.29 is stable.
    @unittest.skip("Skip until staging and prod are on repo v2.29 b/245333797")
    def testGetManifestsBranch(self):
        # pylint: disable=protected-access
        func = git.ManifestCheckout._GetManifestsBranch
        manifest = self.manifest_dir
        repo_root = self.tempdir

        # pylint: disable=unused-argument
        def reconfig(merge="master", origin="origin"):
            if merge is not None:
                merge = "refs/heads/%s" % merge
            for key in ("merge", "origin"):
                val = locals()[key]
                key = "branch.default.%s" % key
                if val is None:
                    git.RunGit(
                        manifest, ["config", "--unset", key], check=False
                    )
                else:
                    git.RunGit(manifest, ["config", key, val])

        # First, verify our assumptions about a fresh repo init are correct.
        self.assertEqual("default", git.GetCurrentBranch(manifest))
        self.assertEqual("master", func(repo_root))

        # Ensure we can handle a missing origin; this can occur jumping between
        # branches, and can be worked around.
        reconfig(origin=None)
        self.assertEqual("default", git.GetCurrentBranch(manifest))
        self.assertEqual("master", func(repo_root))

        def assertExcept(message, **kwargs):
            reconfig(**kwargs)
            self.assertRaises2(
                OSError,
                func,
                repo_root,
                ex_msg=message,
                check_attrs={"errno": errno.ENOENT},
            )

        # No merge target means the configuration isn't usable, period.
        assertExcept(
            "git tracking configuration for that branch is broken", merge=None
        )

        # Ensure we detect if we're on the wrong branch, even if it has
        # tracking setup.
        git.RunGit(manifest, ["checkout", "-t", "origin/master", "-b", "test"])
        assertExcept("It should be checked out to 'default'")

        # Ensure we handle detached HEAD w/ an appropriate exception.
        git.RunGit(manifest, ["checkout", "--detach", "test"])
        assertExcept("It should be checked out to 'default'")

        # Finally, ensure that if the default branch is non-existent, we still
        # throw a usable exception.
        git.RunGit(manifest, ["branch", "-d", "default"])
        assertExcept("It should be checked out to 'default'")

    # TODO(b/245813531): Renable when repo v2.29 is stable.
    @unittest.skip("Skip until staging and prod are on repo v2.29 b/245333797")
    def testGitMatchBranchName(self):
        git_repo = os.path.join(self.tempdir, ".repo", "manifests")

        branches = git.MatchBranchName(git_repo, "default", namespace="")
        self.assertEqual(branches, ["refs/heads/default"])

        branches = git.MatchBranchName(
            git_repo, "default", namespace="refs/heads/"
        )
        self.assertEqual(branches, ["default"])

        branches = git.MatchBranchName(
            git_repo, "origin/f.*link", namespace="refs/remotes/"
        )
        self.assertTrue("firmware-link-" in branches[0])

        branches = git.MatchBranchName(git_repo, "r23")
        self.assertEqual(
            branches,
            [
                "refs/remotes/origin/release-R23-2913.B",
                "refs/remotes/origin/release-R23-2913.B-suffix",
            ],
        )

        branches = git.MatchBranchName(git_repo, "release-R23-2913.B")
        self.assertEqual(branches, ["refs/remotes/origin/release-R23-2913.B"])

        branches = git.MatchBranchName(
            git_repo, "release-R23-2913.B", namespace="refs/remotes/origin/"
        )
        self.assertEqual(branches, ["release-R23-2913.B"])

        branches = git.MatchBranchName(
            git_repo, "release-R23-2913.B", namespace="refs/remotes/"
        )
        self.assertEqual(branches, ["origin/release-R23-2913.B"])


class ManifestHashTest(cros_test_lib.TestCase):
    """Tests for _GetManifestHash functionality."""

    def testGetManifestHashIgnoreMissing(self):
        # pylint: disable=protected-access
        hash_str = git.Manifest._GetManifestHash(
            "absence_file", ignore_missing=True
        )
        self.assertIsNone(hash_str)


class CommitLogTest(cros_test_lib.RunCommandTestCase):
    """Test for Commit log functionality."""

    def testGetLastCommit(self):
        sha = "1323ab4efce4f30f7e3e22f9da27a1a57fa82988"
        commit_date = datetime.datetime.now()
        change_id = "Ia66f15d367ddd386f7c8b47b76b58e3b9f749fce"
        log_output = f"""commit {sha} (HEAD -> default, origin/main, m/main)
Author:     Clark Kent <clark.kent@dc.com>
AuthorDate: {commit_date.isoformat()}
Commit:     DC LUCI <dc-scoped@dc.com>
CommitDate: {commit_date.isoformat()}

    some commit message

    BUG=b:12344322
    TEST=None

    Change-Id: {change_id}
    Reviewed-by: Bruce Wayne <bruce.wayne@dc.com>
"""
        result = cros_build_lib.CompletedProcess(stdout=log_output)
        self.PatchObject(git, "RunGit", return_value=result)

        commit = git.GetLastCommit("git/repo/path")
        self.assertEqual(sha, commit.sha)
        self.assertEqual(commit_date, commit.commit_date)
        self.assertEqual(change_id, commit.change_id)


class CommitEntryTest(cros_test_lib.TestCase):
    """Test CommitEntry class."""

    def testParseFullerToParseGitLog(self):
        # pylint: disable=line-too-long
        log_output = """commit 1323ab4efce4f30f7e3e22f9da27a1a57fa82988 (HEAD -> default, origin/main, m/main)
Author:     Clark Kent <clark.kent@dc.com>
AuthorDate: 2023-08-23T17:41:32+00:00
Commit:     DC LUCI <dc-scoped@dc.com>
CommitDate: 2023-08-24T17:41:32+00:00

    some commit message

    BUG=b:12344322
    TEST=None

    Change-Id: Ia66f15d367ddd386f7c8b47b76b58e3b9f749fce
    Reviewed-by: Bruce Wayne <bruce.wayne@dc.com>

"""
        commits = list(git.CommitEntry.ParseFuller(log_output))

        self.assertEqual(
            commits,
            [
                git.CommitEntry(
                    sha="1323ab4efce4f30f7e3e22f9da27a1a57fa82988",
                    author="Clark Kent <clark.kent@dc.com>",
                    author_date=datetime.datetime.fromisoformat(
                        "2023-08-23T17:41:32+00:00",
                    ),
                    commit="DC LUCI <dc-scoped@dc.com>",
                    commit_date=datetime.datetime.fromisoformat(
                        "2023-08-24T17:41:32+00:00",
                    ),
                    change_id="Ia66f15d367ddd386f7c8b47b76b58e3b9f749fce",
                ),
            ],
        )

    def testParseFullerToParseMultipleCommits(self):
        # pylint: disable=line-too-long
        log_output = """commit 1323ab4efce4f30f7e3e22f9da27a1a57fa82988 (HEAD -> default, origin/main, m/main)
Author:     Clark Kent <clark.kent@dc.com>
AuthorDate: 2023-08-23T17:41:32+00:00
Commit:     DC LUCI <dc-scoped@dc.com>
CommitDate: 2023-08-24T17:41:32+00:00

    some commit message

    BUG=b:12344322
    TEST=None

    Change-Id: Ia66f15d367ddd386f7c8b47b76b58e3b9f749fce
    Reviewed-by: Bruce Wayne <bruce.wayne@dc.com>

commit b4c2c0bbd3d064a87be4c2505aaf54a55d1625e5
Author:     Diana Prince <diana.prince@dc.com>
AuthorDate: 2023-08-23T10:41:32+00:00
Commit:     DC LUCI <dc-scoped@dc.com>
CommitDate: 2023-08-24T15:41:32+00:00

    some commit message

    BUG=b:12344322
    TEST=None

    Change-Id: I22f6f0ed2084a8b9e80ccb2d3b1fc9a3ed18caf7
    Reviewed-by: Bruce Wayne <bruce.wayne@dc.com>
"""
        commits = list(git.CommitEntry.ParseFuller(log_output))

        self.assertEqual(
            commits,
            [
                git.CommitEntry(
                    sha="1323ab4efce4f30f7e3e22f9da27a1a57fa82988",
                    author="Clark Kent <clark.kent@dc.com>",
                    author_date=datetime.datetime.fromisoformat(
                        "2023-08-23T17:41:32+00:00",
                    ),
                    commit="DC LUCI <dc-scoped@dc.com>",
                    commit_date=datetime.datetime.fromisoformat(
                        "2023-08-24T17:41:32+00:00",
                    ),
                    change_id="Ia66f15d367ddd386f7c8b47b76b58e3b9f749fce",
                ),
                git.CommitEntry(
                    sha="b4c2c0bbd3d064a87be4c2505aaf54a55d1625e5",
                    author="Diana Prince <diana.prince@dc.com>",
                    author_date=datetime.datetime.fromisoformat(
                        "2023-08-23T10:41:32+00:00",
                    ),
                    commit="DC LUCI <dc-scoped@dc.com>",
                    commit_date=datetime.datetime.fromisoformat(
                        "2023-08-24T15:41:32+00:00",
                    ),
                    change_id="I22f6f0ed2084a8b9e80ccb2d3b1fc9a3ed18caf7",
                ),
            ],
        )
