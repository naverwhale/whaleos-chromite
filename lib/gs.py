# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Library to make common google storage operations more reliable."""

import collections
import contextlib
import datetime
import errno
import fnmatch
import getpass
import hashlib
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, NamedTuple, Optional
import urllib.parse

from chromite.lib import cache
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.lib import path_util
from chromite.lib import retry_stats
from chromite.lib import retry_util
from chromite.lib import signals
from chromite.lib import timeout_util
from chromite.utils import gs_urls_util
from chromite.utils import key_value_store


# This bucket has the allAuthenticatedUsers:READER ACL.
AUTHENTICATION_BUCKET = "gs://chromeos-authentication-bucket/"

# Format used by "gsutil ls -l" when reporting modified time.
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# Regexp for parsing each line of output from "gsutil ls -l".
# This regexp is prepared for the generation and meta_generation values,
# too, even though they are not expected until we use "-a".
#
# A detailed listing looks like:
#    99908  2014-03-01T05:50:08Z  gs://bucket/foo/abc#1234  metageneration=1
#                                 gs://bucket/foo/adir/
#    99908  2014-03-04T01:16:55Z  gs://bucket/foo/def#5678  metageneration=1
# TOTAL: 2 objects, 199816 bytes (495.36 KB)
LS_LA_RE = re.compile(
    r"^\s*(?P<content_length>\d*?)\s+"
    r"(?P<creation_time>\S*?)\s+"
    r"(?P<url>[^#$]+).*?"
    r"("
    r"#(?P<generation>\d+)\s+"
    r"meta_?generation=(?P<metageneration>\d+)"
    r")?\s*$"
)
LS_RE = re.compile(
    r"^\s*(?P<content_length>)(?P<creation_time>)(?P<url>.*)"
    r"(?P<generation>)(?P<metageneration>)\s*$"
)

# Format used by ContainsWildCard, which is duplicated from
# https://github.com/GoogleCloudPlatform/gsutil/blob/v4.21/gslib/storage_url.py#L307.
WILDCARD_REGEX = re.compile(r"[*?\[\]]")


class GSContextException(Exception):
    """Base exception for all exceptions thrown by GSContext."""


# Since the underlying code uses run, some callers might be trying to
# catch cros_build_lib.RunCommandError themselves.  Extend that class so that
# code continues to work.
class GSCommandError(GSContextException, cros_build_lib.RunCommandError):
    """Thrown when an error happened we couldn't decode."""


class GSContextPreconditionFailed(GSContextException):
    """Thrown when google storage returns code=PreconditionFailed."""


class GSNoSuchKey(GSContextException):
    """Thrown when google storage returns code=NoSuchKey."""


class GSAuthenticationError(GSContextException):
    """Thrown when the user is unable to authenticate"""


# Detailed results of GSContext.Stat.
#
# The fields directory correspond to gsutil stat results.
#
#  Field name        Type         Example
#   creation_time     datetime     Sat, 23 Aug 2014 06:53:20 GMT
#   content_length    int          74
#   content_type      string       application/octet-stream
#   hash_crc32c       string       BBPMPA==
#   hash_md5          string       ms+qSYvgI9SjXn8tW/5UpQ==
#   etag              string       CNCgocbmqMACEAE=
#   generation        int          1408776800850000
#   metageneration    int          1
#
# Note: We omit a few stat fields as they are not always available, and we
# have no callers that want this currently.
#
#   content_language  string/None  en   # This field may be None.
GSStatResult = collections.namedtuple(
    "GSStatResult",
    (
        "creation_time",
        "content_length",
        "content_type",
        "hash_crc32c",
        "hash_md5",
        "etag",
        "generation",
        "metageneration",
    ),
)


class GSListResult(NamedTuple):
    """Detailed results of GSContext.List."""

    url: str
    creation_time: Optional[int] = None
    content_length: Optional[int] = None
    generation: Optional[int] = None
    metageneration: Optional[int] = None


class ErrorDetails(NamedTuple):
    """Detailed errors for internal gsutil output processing."""

    type: str
    retriable: bool
    message_pattern: Optional[str] = ""
    exception: Optional[GSContextException] = None


class GSCounter:
    """A counter class for Google Storage."""

    def __init__(self, ctx, path):
        """Create a counter object.

        Args:
            ctx: A GSContext object.
            path: The path to the counter in Google Storage.
        """
        self.ctx = ctx
        self.path = path

    def Get(self):
        """Get the current value of a counter."""
        try:
            return int(self.ctx.Cat(self.path))
        except GSNoSuchKey:
            return 0

    def AtomicCounterOperation(self, default_value, operation):
        """Atomically set the counter value using |operation|.

        Args:
            default_value: Default value to use for counter, if counter does not
                exist.
            operation: Function that takes the current counter value as a
                parameter, and returns the new desired value.

        Returns:
            The new counter value. None if value could not be set.
        """
        generation, _ = self.ctx.GetGeneration(self.path)
        for _ in range(self.ctx.retries + 1):
            try:
                value = (
                    default_value if generation == 0 else operation(self.Get())
                )
                self.ctx.Copy(
                    "-", self.path, input=str(value), version=generation
                )
                return value
            except (GSContextPreconditionFailed, GSNoSuchKey):
                # GSContextPreconditionFailed is thrown if another builder is
                # also trying to update the counter, and we lost the race.
                # GSNoSuchKey is thrown if another builder deleted the counter.
                # In either case, fetch the generation again, and, if it has
                # changed, try the copy again.
                new_generation, _ = self.ctx.GetGeneration(self.path)
                if new_generation == generation:
                    raise
                generation = new_generation

    def Increment(self):
        """Increment the counter.

        Returns:
            The new counter value. None if value could not be set.
        """
        return self.AtomicCounterOperation(1, lambda x: x + 1)

    def Decrement(self):
        """Decrement the counter.

        Returns:
            The new counter value. None if value could not be set.
        """
        return self.AtomicCounterOperation(-1, lambda x: x - 1)

    def Reset(self):
        """Reset the counter to zero.

        Returns:
            The new counter value. None if value could not be set.
        """
        return self.AtomicCounterOperation(0, lambda x: 0)

    def StreakIncrement(self):
        """Increment the counter if it is positive, otherwise set it to 1.

        Returns:
            The new counter value. None if value could not be set.
        """
        return self.AtomicCounterOperation(1, lambda x: x + 1 if x > 0 else 1)

    def StreakDecrement(self):
        """Decrement the counter if it is negative, otherwise set it to -1.

        Returns:
            The new counter value. None if value could not be set.
        """
        return self.AtomicCounterOperation(-1, lambda x: x - 1 if x < 0 else -1)


class GSContext:
    """A class to wrap common google storage operations."""

    # Error messages that indicate an invalid BOTO config.
    AUTHORIZATION_ERRORS = (
        "no configured",
        "none configured",
        "detail=Authorization",
        "401 Anonymous caller",
    )

    DEFAULT_BOTO_FILE = os.path.expanduser("~/.boto")
    DEFAULT_GSUTIL_TRACKER_DIR = os.path.expanduser("~/.gsutil/tracker-files")
    # This is set for ease of testing.
    _DEFAULT_GSUTIL_BIN = None
    _DEFAULT_GSUTIL_BUILDER_BIN = "/b/build/third_party/gsutil/gsutil"
    _CRCMOD_METHOD = None
    # How many times to retry uploads.
    DEFAULT_RETRIES = 3

    # Multiplier for how long to sleep (in seconds) between retries; will delay
    # (1*sleep) the first time, then (2*sleep), continuing via attempt * sleep.
    DEFAULT_SLEEP_TIME = 60

    GSUTIL_VERSION = "5.23"
    GSUTIL_TAR = "gsutil_%s.tar.gz" % GSUTIL_VERSION
    GSUTIL_URL = (
        gs_urls_util.PUBLIC_BASE_HTTPS_URL
        + "chromeos-mirror/gentoo/distfiles/%s" % GSUTIL_TAR
    )
    GSUTIL_API_SELECTOR = "JSON"

    RESUMABLE_UPLOAD_ERROR = (
        b"Too many resumable upload attempts failed " b"without progress"
    )
    RESUMABLE_DOWNLOAD_ERROR = (
        b"Too many resumable download attempts failed " b"without progress"
    )

    # TODO: Below is a list of known flaky errors that we should
    # retry. The list needs to be extended.
    RESUMABLE_ERROR_MESSAGE = (
        RESUMABLE_DOWNLOAD_ERROR,
        RESUMABLE_UPLOAD_ERROR,
        b"ResumableUploadException",
        b"ResumableUploadAbortException",
        b"ResumableDownloadException",
        b"ssl.SSLError: The read operation timed out",
        # TODO: Error messages may change in different library versions,
        # use regexes to match resumable error messages.
        b"ssl.SSLError: ('The read operation timed out',)",
        b"ssl.SSLError: _ssl.c:495: The handshake operation timed out",
        b"Unable to find the server",
        b"doesn't match cloud-supplied digest",
        b"ssl.SSLError: [Errno 8]",
        b"EOF occurred in violation of protocol",
        # TODO(nxia): crbug.com/775330 narrow down the criteria for retrying
        b"AccessDeniedException",
    )

    # We have seen flaky errors with 5xx return codes
    # See b/17376491 for the "JSON decoding" error.
    # We have seen transient Oauth 2.0 credential errors (crbug.com/414345).
    TRANSIENT_ERROR_MESSAGE = (
        b"ServiceException: 5",
        b"Failure: No JSON object could be decoded",
        b"Oauth 2.0 User Account",
        b"InvalidAccessKeyId",
        b"socket.error: [Errno 104] Connection reset by peer",
        b"Received bad request from server",
        b"can't start new thread",
        # See: b/197574857.
        b"OSError: None",
        b"cannot read from timed out object",
    )

    @classmethod
    def InitializeCache(cls, cache_dir=None, cache_user=None):
        """Setup the gsutil cache if needed."""
        if cls._DEFAULT_GSUTIL_BIN is not None:
            return

        if cache_dir is None:
            cache_dir = path_util.GetCacheDir()
        if cache_dir is not None:
            common_path = os.path.join(cache_dir, constants.COMMON_CACHE)
            tar_cache = cache.TarballCache(common_path, cache_user=cache_user)
            key = (cls.GSUTIL_TAR,)
            # The common cache will not be LRU, removing the need to hold a read
            # lock on the cached gsutil.
            ref = tar_cache.Lookup(key)
            ref.SetDefault(cls.GSUTIL_URL)
            cls._DEFAULT_GSUTIL_BIN = os.path.join(ref.path, "gsutil", "gsutil")
            cls._DetermineCrcmodStrategy(Path(ref.path))
        else:
            # Check if the default gsutil path for builders exists. If
            # not, try locating gsutil. If none exists, simply use 'gsutil'.
            gsutil_bin = cls._DEFAULT_GSUTIL_BUILDER_BIN
            if not os.path.exists(gsutil_bin):
                gsutil_bin = osutils.Which("gsutil")
            if gsutil_bin is None:
                gsutil_bin = "gsutil"
            cls._DEFAULT_GSUTIL_BIN = gsutil_bin

    @classmethod
    def _DetermineCrcmodStrategy(cls, path: Path):
        """Figure out how we'll get a compiled crcmod.

        The compiled crcmod code is much faster than the python implementation,
        and enables some more features (otherwise gsutil internally disables
        them). Try to compile the module on demand in the crcmod tree bundled
        with gsutil.

        If that's not working, we'll try to fall back to vpython when available.

        For more details, see:
        https://cloud.google.com/storage/docs/gsutil/addlhelp/CRC32CandInstallingcrcmod

        Args:
            path: The path to our local copy of gsutil.

        Returns:
            'import' if the active python has it available already (whoo!).
            'bundle' if we were able to build the bundled copy in the gsutil
                source.
            'vpython' if we need to use vpython to pull a wheel on the fly.
            'missing' if we weren't able to find a compiled version.
        """
        if cls._CRCMOD_METHOD is not None:
            return cls._CRCMOD_METHOD

        # See if the system includes one in which case we're done.
        # We'll use the active python interp to run gsutil directly.
        try:
            from crcmod.crcmod import _usingExtension

            if _usingExtension:
                cls._CRCMOD_METHOD = "import"
                return cls._CRCMOD_METHOD
        except ImportError:
            pass

        # Try to compile the bundled copy.
        if cls._SetupBundledCrcmod(path):
            cls._CRCMOD_METHOD = "bundle"
            return cls._CRCMOD_METHOD

        # Give vpython a chance if it exists.
        if cls._SetupVpython(path):
            cls._CRCMOD_METHOD = "vpython"
            return cls._CRCMOD_METHOD

        cls._CRCMOD_METHOD = "missing"
        return cls._CRCMOD_METHOD

    @classmethod
    def _SetupBundledCrcmod(cls, path: Path) -> bool:
        """Try to setup a compiled crcmod for gsutil."""
        src_root = path / "gsutil" / "third_party" / "crcmod"

        # See if module already exists.
        try:
            next(src_root.glob("python3/crcmod/_crcfunext*.so"))
            return True
        except StopIteration:
            pass

        # Try to build it once.
        flag = src_root / ".chromite.tried.build"
        if flag.exists():
            return False
        # Flag things now regardless of how the attempt below works out.
        try:
            osutils.Touch(flag)
        except IOError as e:
            # If the gsutil dir was cached previously as root, but now we're
            # non-root, just flag it and return.
            if e.errno == errno.EACCES:
                logging.debug(
                    "Skipping gsutil crcmod compile due to permissions"
                )
                cros_build_lib.sudo_run(
                    ["touch", str(flag)], debug_level=logging.DEBUG
                )
                return False
            else:
                raise

        # See if the local copy has one.
        logging.debug("Attempting to compile local crcmod for gsutil")
        with osutils.TempDir(prefix="chromite.gsutil.crcmod") as tempdir:
            tempdir = Path(tempdir)
            result = cros_build_lib.run(
                [
                    sys.executable,
                    "setup.py",
                    "build",
                    "--build-base",
                    str(tempdir),
                    "--build-platlib",
                    str(tempdir),
                ],
                cwd=src_root,
                capture_output=True,
                check=False,
                debug_level=logging.DEBUG,
            )
            if result.returncode:
                return False

            # Locate the module in the build dir.
            copied = False
            for mod_path in tempdir.glob("crcmod/_crcfunext*.so"):
                dst_mod_path = src_root / "python3" / "crcmod" / mod_path.name
                try:
                    shutil.copy2(mod_path, dst_mod_path)
                    copied = True
                except shutil.Error:
                    pass

            if not copied:
                # If the module compile failed (missing
                # compiler/headers/whatever), then the setup.py build command
                # above would have passed, but there won't actually be a
                # _crcfunext.so module.  Check for it here to disambiguate other
                # errors from shutil.copy2.
                logging.debug(
                    "No crcmod module produced (missing host compiler?)"
                )

            return copied

    @classmethod
    def _SetupVpython(cls, path: Path) -> bool:
        """Setup a vpython spec to use later on."""
        if not osutils.Which("vpython3"):
            return False

        spec = path / "gsutil" / "gsutil.vpython3"
        if spec.exists():
            return True
        data = b"""python_version: "3.8"
wheel: <
  name: "infra/python/wheels/crcmod/${vpython_platform}"
  version: "version:1.7"
>
"""
        # TODO(vapier): Drop str() once WriteFile accepts Path objects.
        spec = str(spec)
        try:
            osutils.WriteFile(spec, data, mode="wb", atomic=True)
        except OSError:
            # If the cache already existed, as root, but hadn't had the spec
            # written, do it as root now.
            osutils.WriteFile(spec, data, mode="wb", atomic=True, sudo=True)
        return True

    def __init__(
        self,
        boto_file=None,
        cache_dir=None,
        acl=None,
        dry_run=False,
        gsutil_bin=None,
        init_boto=False,
        retries=None,
        sleep=None,
        cache_user=None,
    ):
        """Constructor.

        Args:
            boto_file: Fully qualified path to user's .boto credential file.
            cache_dir: The absolute path to the cache directory. Use the default
                fallback if not given.
            acl: If given, a canned ACL. It is not valid to pass in an ACL file
                here, because most gsutil commands do not accept ACL files. If
                you would like to use an ACL file, use the SetACL command
                instead.
            dry_run: Testing mode that prints commands that would be run.
            gsutil_bin: If given, the absolute path to the gsutil binary.  Else
                the default fallback will be used.
            init_boto: If set to True, GSContext will check during __init__ if a
                valid boto config is configured, and if not, will attempt to ask
                the user to interactively set up the boto config.
            retries: Number of times to retry a command before failing.
            sleep: Amount of time to sleep between failures.
            cache_user: user for creating cache_dir for gsutil. Default is None.
        """
        if gsutil_bin is None:
            self.InitializeCache(cache_dir=cache_dir, cache_user=cache_user)
            gsutil_bin = self._DEFAULT_GSUTIL_BIN
            if self._CRCMOD_METHOD == "vpython":
                self._gsutil_bin = ["vpython3", gsutil_bin]
            else:
                self._gsutil_bin = [sys.executable, gsutil_bin]
        else:
            self._CheckFile("gsutil not found", gsutil_bin)
            self._gsutil_bin = [gsutil_bin]

        # The version of gsutil is retrieved on demand and cached here.
        self._gsutil_version = None

        # Increase the number of retries. With 10 retries, Boto will try a total
        # of 11 times and wait up to 2**11 seconds (~30 minutes) in total, not
        # including the time spent actually uploading or downloading.
        self.gsutil_flags = ["-o", "Boto:num_retries=10"]

        # Set HTTP proxy if environment variable http_proxy is set
        # (crbug.com/325032).
        if "http_proxy" in os.environ:
            url = urllib.parse.urlparse(os.environ["http_proxy"])
            if not url.hostname or (not url.username and url.password):
                logging.warning(
                    "GS_ERROR: Ignoring env variable http_proxy because it "
                    "is not properly set: %s",
                    os.environ["http_proxy"],
                )
            else:
                self.gsutil_flags += ["-o", "Boto:proxy=%s" % url.hostname]
                if url.username:
                    self.gsutil_flags += [
                        "-o",
                        "Boto:proxy_user=%s" % url.username,
                    ]
                if url.password:
                    self.gsutil_flags += [
                        "-o",
                        "Boto:proxy_pass=%s" % url.password,
                    ]
                if url.port:
                    self.gsutil_flags += ["-o", "Boto:proxy_port=%d" % url.port]

        # Prefer boto_file if specified, else prefer the env then the default.
        if boto_file is None:
            boto_file = os.environ.get("BOTO_CONFIG")
        if boto_file is None and os.path.isfile(self.DEFAULT_BOTO_FILE):
            # Only set boto file to DEFAULT_BOTO_FILE if it exists.
            boto_file = self.DEFAULT_BOTO_FILE

        self.boto_file = boto_file

        self.acl = acl

        self.dry_run = dry_run
        self.retries = self.DEFAULT_RETRIES if retries is None else int(retries)
        self._sleep_time = (
            self.DEFAULT_SLEEP_TIME if sleep is None else int(sleep)
        )

        if init_boto and not dry_run:
            # We can't really expect gsutil to even be present in dry_run mode.
            self._InitBoto()

    @property
    def gsutil_version(self):
        """Return the version of the gsutil in this context."""
        if not self._gsutil_version:
            if self.dry_run:
                self._gsutil_version = self.GSUTIL_VERSION
            else:
                cmd = ["-q", "version"]

                # gsutil has been known to return version to stderr in the past,
                # so use stderr=subprocess.STDOUT.
                result = self.DoCommand(
                    cmd, stdout=True, stderr=subprocess.STDOUT
                )

                # Expect output like: 'gsutil version 3.35' or
                # 'gsutil version: 4.5'.
                match = re.search(
                    r"^\s*gsutil\s+version:?\s+([\d.]+)",
                    result.stdout,
                    re.IGNORECASE,
                )
                if match:
                    self._gsutil_version = match.group(1)
                else:
                    raise GSContextException(
                        'Unexpected output format from "%s":\n%s.'
                        % (result.cmdstr, result.stdout)
                    )

        return self._gsutil_version

    def _CheckFile(self, errmsg, afile):
        """Pre-flight check for valid inputs.

        Args:
            errmsg: Error message to display.
            afile: Fully qualified path to test file existence.
        """
        if not os.path.isfile(afile):
            raise GSContextException("%s, %s is not a file" % (errmsg, afile))

    def _TestGSLs(self, path=AUTHENTICATION_BUCKET, **kwargs):
        """Quick test of gsutil functionality."""
        # The AUTHENTICATION_BUCKET is readable by any authenticated account.
        # If we can list its contents, we have valid authentication.
        cmd = ["ls", path]
        kwargs.setdefault("stdout", True)
        kwargs.setdefault("stderr", True)
        result = self.DoCommand(
            cmd,
            retries=0,
            debug_level=logging.DEBUG,
            check=False,
            **kwargs,
        )

        if result.returncode == 1 and not kwargs["stderr"]:
            return False

        # Did we fail with an authentication error?
        if kwargs["stderr"] and any(
            e in result.stderr for e in self.AUTHORIZATION_ERRORS
        ):
            logging.warning(
                "gsutil authentication failure msg: %s", result.stderr
            )
            return False

        return True

    def _ConfigureBotoConfig(self):
        """Make sure we can access protected bits in GS."""
        print("Configuring gsutil. **Please use your @google.com account.**")
        try:
            if not self.boto_file:
                self.boto_file = self.DEFAULT_BOTO_FILE
            self.DoCommand(
                ["config"],
                retries=0,
                debug_level=logging.CRITICAL,
                print_cmd=False,
            )
        finally:
            if os.path.exists(self.boto_file) and not os.path.getsize(
                self.boto_file
            ):
                os.remove(self.boto_file)
                raise GSContextException("GS config could not be set up.")

    def _InitBoto(self):
        if not self._TestGSLs():
            self._ConfigureBotoConfig()

    def Cat(self, path, **kwargs):
        """Returns the contents of a GS object."""
        kwargs.setdefault("stdout", True)
        encoding = kwargs.setdefault("encoding", None)
        errors = kwargs.setdefault("errors", None)
        if not gs_urls_util.PathIsGs(path):
            # gsutil doesn't support cat-ting a local path, so read it
            # ourselves.
            mode = "rb" if encoding is None else "r"
            try:
                return osutils.ReadFile(
                    path, mode=mode, encoding=encoding, errors=errors
                )
            except Exception as e:
                if getattr(e, "errno", None) == errno.ENOENT:
                    raise GSNoSuchKey(
                        "Cat Error: file %s does not exist" % path
                    )
                else:
                    raise GSContextException(str(e))
        elif self.dry_run:
            return b"" if encoding is None else ""
        else:
            return self.DoCommand(["cat", path], **kwargs).stdout

    def StreamingCat(self, path, chunksize=0x100000):
        """Returns the content of a GS file as a stream.

        Unlike Cat or Copy, this function doesn't support any internal retry or
        validation by computing checksum of downloaded data. Users should
        perform their own validation, or use Cat() instead.

        Args:
            path: Full gs:// path of the src file.
            chunksize: At most how much data read from upstream and yield to
                callers at a time. The default value is 1 MB.

        Yields:
            The file content, chunk by chunk, as bytes.
        """
        assert gs_urls_util.PathIsGs(path)

        if self.dry_run:
            return (lambda: (yield ""))()

        env = None
        if self.boto_file and os.path.isfile(self.boto_file):
            env = os.environ.copy()
            env["BOTO_CONFIG"] = self.boto_file

        cmd = self._gsutil_bin + self.gsutil_flags + ["cat", path]
        proc = subprocess.Popen(  # pylint: disable=consider-using-with
            cmd, stdout=subprocess.PIPE, env=env
        )

        def read_content():
            try:
                while True:
                    data = proc.stdout.read(chunksize)
                    if not data and proc.poll() is not None:
                        break
                    if data:
                        yield data

                rc = proc.poll()
                if rc:
                    raise GSCommandError(
                        "Cannot stream cat %s from Google Storage!" % path,
                        rc,
                        None,
                    )
            finally:
                if proc.returncode is None:
                    proc.stdout.close()
                    proc.terminate()

        return read_content()

    def CopyInto(self, local_path, remote_dir, filename=None, **kwargs):
        """Upload a local file into a directory in google storage.

        Args:
            local_path: Local file path to copy.
            remote_dir: Full gs:// url of the directory to transfer the file
                into.
            filename: If given, the filename to place the content at; if not
                given, it's discerned from basename(local_path).
            **kwargs: See Copy() for documentation.

        Returns:
            The generation of the remote file.
        """
        filename = filename if filename is not None else local_path
        # Basename it even if an explicit filename was given; we don't want
        # people using filename as a multi-directory path fragment.
        return self.Copy(
            local_path,
            "%s/%s" % (remote_dir, os.path.basename(filename)),
            **kwargs,
        )

    @staticmethod
    def GetTrackerFilenames(dest_path):
        """Returns a list of gsutil tracker filenames.

        Tracker files are used by gsutil to resume downloads/uploads. This
        function does not handle parallel uploads.

        Args:
            dest_path: Either a GS path or an absolute local path.

        Returns:
            The list of potential tracker filenames.
        """
        dest = urllib.parse.urlsplit(dest_path)
        filenames = []
        if dest.scheme == "gs":
            prefix = "upload"
            bucket_name = dest.netloc
            object_name = dest.path.lstrip("/")
            filenames.append(
                re.sub(
                    r"[/\\]",
                    "_",
                    "resumable_upload__%s__%s__%s.url"
                    % (bucket_name, object_name, GSContext.GSUTIL_API_SELECTOR),
                )
            )
        else:
            prefix = "download"
            filenames.append(
                re.sub(
                    r"[/\\]",
                    "_",
                    "resumable_download__%s__%s.etag"
                    % (dest.path, GSContext.GSUTIL_API_SELECTOR),
                )
            )

        hashed_filenames = []
        for filename in filenames:
            m = hashlib.sha1(filename.encode())
            hashed_filenames.append(
                "%s_TRACKER_%s.%s" % (prefix, m.hexdigest(), filename[-16:])
            )

        return hashed_filenames

    def _RetryFilter(self, e):
        """Returns whether to retry RunCommandError exception |e|.

        Args:
            e: Exception object to filter. Exception may be re-raised as a
                different type, if _RetryFilter determines a more appropriate
                exception type based on the contents of |e|.
        """
        error_details = self._MatchKnownError(e)
        if error_details.exception:
            raise error_details.exception
        return error_details.retriable

    def _MatchKnownError(self, e):
        """Function to match known RunCommandError exceptions.

        Args:
            e: Exception object to filter.

        Returns:
            An ErrorDetails instance with details about the message pattern
            found.
        """
        if not retry_util.ShouldRetryCommandCommon(e):
            if not isinstance(e, cros_build_lib.RunCommandError):
                error_type = "unknown"
            else:
                error_type = "failed_to_launch"
            return ErrorDetails(type=error_type, retriable=False)

        # e is guaranteed by above filter to be a RunCommandError
        if e.returncode < 0:
            sig_name = signals.StrSignal(-e.returncode)
            logging.info(
                "Child process received signal %d; not retrying.", sig_name
            )
            return ErrorDetails(
                type="received_signal",
                message_pattern=sig_name,
                retriable=False,
            )

        error = e.stderr
        if error:
            # Since the captured error will use the encoding the user requested,
            # normalize to bytes for testing below.
            if isinstance(error, str):
                error = error.encode("utf-8")

            # gsutil usually prints PreconditionException when a precondition
            # fails. It may also print "ResumableUploadAbortException: 412
            # Precondition Failed", so the logic needs to be a little more
            # general.
            if (
                b"PreconditionException" in error
                or b"412 Precondition Failed" in error
            ):
                return ErrorDetails(
                    type="precondition_exception",
                    retriable=False,
                    exception=GSContextPreconditionFailed(e),
                )

            # If the file does not exist, one of the following errors occurs.
            # The "stat" command leaves off the "CommandException: " prefix, but
            # it also outputs to stdout instead of stderr and so will not be
            # caught here regardless.
            if (
                b"CommandException: No URLs matched" in error
                or b"NotFoundException:" in error
                or b"One or more URLs matched no objects" in error
            ):
                return ErrorDetails(
                    type="no_such_key",
                    retriable=False,
                    exception=GSNoSuchKey(e),
                )

            logging.warning("GS_ERROR: %s ", error)

            # Temporary fix: remove the gsutil tracker files so that our retry
            # can hit a different backend. This should be removed after the
            # bug is fixed by the Google Storage team (see crbug.com/308300).
            resumable_error = _FirstSubstring(
                error, self.RESUMABLE_ERROR_MESSAGE
            )
            if resumable_error:
                # Only remove the tracker files if we try to upload/download a
                # file.
                if "cp" in e.cmd[:-2]:
                    # Assume a command: gsutil [options] cp [options] src_path
                    # dest_path dest_path needs to be a fully qualified local
                    # path, which is already required for GSContext.Copy().
                    tracker_filenames = self.GetTrackerFilenames(e.cmd[-1])
                    logging.info(
                        "Potential list of tracker files: %s", tracker_filenames
                    )
                    for tracker_filename in tracker_filenames:
                        tracker_file_path = os.path.join(
                            self.DEFAULT_GSUTIL_TRACKER_DIR, tracker_filename
                        )
                        if os.path.exists(tracker_file_path):
                            logging.info(
                                "Deleting gsutil tracker file %s before "
                                "retrying.",
                                tracker_file_path,
                            )
                            logging.info(
                                "The content of the tracker file: %s",
                                osutils.ReadFile(tracker_file_path),
                            )
                            osutils.SafeUnlink(tracker_file_path)
                return ErrorDetails(
                    type="resumable",
                    message_pattern=resumable_error.decode("utf-8"),
                    retriable=True,
                )

            transient_error = _FirstSubstring(
                error, self.TRANSIENT_ERROR_MESSAGE
            )
            if transient_error:
                return ErrorDetails(
                    type="transient",
                    message_pattern=transient_error.decode("utf-8"),
                    retriable=True,
                )

        return ErrorDetails(type="unknown", retriable=False)

    def CheckPathAccess(self, path: str) -> None:
        """Check that the user can access a given gs path

        Prompts the user to reauthenticate if not.

        Args:
            path: The gspath to check if we can access

        Raises:
            GsAuthenticationError: If we don't have access to the path.
        """
        # Attempt to LS the path, prompting the user for
        # reauthentication if necessary.
        self._TestGSLs(path, stdout=True, stderr=False)
        # Attempt to LS the path again, but this time capture
        # the input so we can verify if we authenticated correctly.
        if not self._TestGSLs(path):
            logging.warning(
                "Unable to access %s "
                "Running `gcloud auth login` may resolve the problem. "
                "For more information, see "
                "https://chromium.googlesource.com"
                "/chromiumos/docs/+/HEAD/gsutil.md#setup",
                path,
            )
            raise GSAuthenticationError(f"Unable to access path: {path}")

    # TODO(mtennant): Make a private method.
    def DoCommand(
        self,
        gsutil_cmd,
        headers=(),
        retries=None,
        version=None,
        parallel=False,
        **kwargs,
    ):
        """Run a gsutil command, suppressing output, and setting retry/sleep.

        Args:
            gsutil_cmd: The (mostly) constructed gsutil subcommand to run.
            headers: A list of raw headers to pass down.
            parallel: Whether gsutil should enable parallel copy/update of
                multiple files. NOTE: This option causes gsutil to use
                significantly more memory, even if gsutil is only uploading one
                file.
            retries: How many times to retry this command (defaults to setting
                given at object creation).
            version: If given, the generation; essentially the timestamp of the
                last update.  Note this is not the same as sequence-number; it's
                monotonically increasing bucket wide rather than reset per file.
                The usage of this is if we intend to replace/update only if the
                version is what we expect.  This is useful for distributed
                reasons - for example, to ensure you don't overwrite someone
                else's creation, a version of 0 states "only update if no
                version exists".

        Returns:
            A CompletedProcess object.
        """
        kwargs = kwargs.copy()
        if "capture_output" not in kwargs:
            kwargs.setdefault("stderr", True)
        kwargs.setdefault("encoding", "utf-8")

        cmd = self._gsutil_bin + self.gsutil_flags
        for header in headers:
            cmd += ["-h", header]
        if version is not None:
            cmd += ["-h", "x-goog-if-generation-match:%d" % int(version)]

        # Enable parallel copy/update of multiple files if stdin is not to
        # be piped to the command. This does not split a single file into
        # smaller components for upload.
        if parallel and kwargs.get("input") is None:
            cmd += ["-m"]

        cmd.extend(gsutil_cmd)

        if retries is None:
            retries = self.retries

        extra_env = kwargs.pop("extra_env", {})
        if self.boto_file and os.path.isfile(self.boto_file):
            extra_env.setdefault("BOTO_CONFIG", self.boto_file)

        if self.dry_run:
            logging.debug(
                "%s: would've run: %s",
                self.__class__.__name__,
                cros_build_lib.CmdToStr(cmd),
            )
        else:
            if "PYTEST_CURRENT_TEST" in os.environ:
                from chromite.lib import cros_test_lib

                # Only allow tests to call us directly when network tests are
                # enabled.  If they're disabled, require that the APIs be mocked
                # to avoid trying to talk to the actual network.
                assert (
                    cros_test_lib.NETWORK_TESTS_ENABLED
                    or hasattr(GSContext.DoCommand, "mock")
                    or hasattr(cros_build_lib.run, "mock")
                    or hasattr(retry_stats.RetryWithStats, "mock")
                ), "GSContext mock missing"
                print(cmd)

            try:
                return retry_stats.RetryWithStats(
                    retry_stats.GSUTIL,
                    self._RetryFilter,
                    retries,
                    cros_build_lib.run,
                    cmd,
                    sleep=self._sleep_time,
                    extra_env=extra_env,
                    **kwargs,
                )
            except cros_build_lib.RunCommandError as e:
                raise GSCommandError(e.msg, e.result, e.exception)

    def Copy(
        self,
        src_path,
        dest_path,
        acl=None,
        recursive=False,
        skip_symlinks=True,
        auto_compress=False,
        **kwargs,
    ):
        """Copy to/from GS bucket.

        Canned ACL permissions can be specified on the gsutil cp command line.

        More info:
        https://developers.google.com/storage/docs/accesscontrol#applyacls

        Args:
            src_path: Fully qualified local path or full gs:// path of the src
                file.
            dest_path: Fully qualified local path or full gs:// path of the dest
                file.
            acl: One of the Google Storage canned_acls to apply.
            recursive: Whether to copy recursively.
            skip_symlinks: Skip symbolic links when copying recursively.
            auto_compress: Automatically compress with gzip when uploading.

        Returns:
            The generation of the remote file.

        Raises:
            RunCommandError if the command failed despite retries.
        """
        # -v causes gs://bucket/path#generation to be listed in output.
        cmd = ["cp", "-v"]

        # Certain versions of gsutil (at least 4.3) assume the source of a copy
        # is a directory if the -r option is used. If it's really a file, gsutil
        # will look like it's uploading it but not actually do anything. We'll
        # work around that problem by suppressing the -r flag if we detect the
        # source is a local file.
        if recursive and not os.path.isfile(src_path):
            cmd.append("-r")
            if skip_symlinks:
                cmd.append("-e")

        if auto_compress:
            cmd.append("-Z")

        acl = self.acl if acl is None else acl
        if acl is not None:
            cmd += ["-a", acl]

        with contextlib.ExitStack() as stack:
            # Write the input into a tempfile if possible. This is needed so
            # that gsutil can retry failed requests.  We allow the input to be a
            # string or bytes regardless of the output encoding.
            if src_path == "-" and kwargs.get("input") is not None:
                f = stack.enter_context(tempfile.NamedTemporaryFile(mode="wb"))
                data = kwargs["input"]
                if isinstance(data, str):
                    data = data.encode("utf-8")
                f.write(data)
                f.flush()
                del kwargs["input"]
                src_path = f.name

            cmd += ["--", src_path, dest_path]

            if not (
                gs_urls_util.PathIsGs(src_path)
                or gs_urls_util.PathIsGs(dest_path)
            ):
                # Don't retry on local copies.
                kwargs.setdefault("retries", 0)

            if "capture_output" not in kwargs:
                kwargs.setdefault("stderr", True)
                kwargs.setdefault("stdout", True)
            try:
                result = self.DoCommand(cmd, **kwargs)
                if self.dry_run:
                    return None

                # Now we parse the output for the current generation number.
                # Example:
                #   Created: gs://example-bucket/foo#1360630664537000.1
                m = re.search(r"Created: .*#(\d+)([.](\d+))?\n", result.stderr)
                if m:
                    return int(m.group(1))
                else:
                    return None
            except GSNoSuchKey as e:
                # If the source was a local file, the error is a quirk of gsutil
                # 4.5 and should be ignored. If the source was remote, there
                # might legitimately be no such file. See crbug.com/393419.
                if os.path.isfile(src_path):
                    return None

                # Temp log for crbug.com/642986, should be removed when the bug
                # is fixed.
                logging.warning(
                    "Copy Error: src %s dest %s: %s "
                    "(Temp log for crbug.com/642986)",
                    src_path,
                    dest_path,
                    e,
                )
                raise

    def CreateWithContents(self, gs_uri, contents, **kwargs):
        """Creates the specified file with specified contents.

        Args:
            gs_uri: The URI of a file on Google Storage.
            contents: String or bytes with contents to write to the file.
            **kwargs: See additional options that Copy takes.

        Raises:
            See Copy.
        """
        self.Copy("-", gs_uri, input=contents, **kwargs)

    # TODO: Merge LS() and List()?
    def LS(self, path, **kwargs):
        """Does a directory listing of the given gs path.

        Args:
            path: The path to get a listing of.
            **kwargs: See options that DoCommand takes.

        Returns:
            A list of paths that matched |path|.  Might be more than one if a
            directory or path include wildcards/etc...
        """
        if self.dry_run:
            return []

        if not gs_urls_util.PathIsGs(path):
            # gsutil doesn't support listing a local path, so just run 'ls'.
            kwargs.pop("retries", None)
            kwargs.pop("headers", None)
            if "capture_output" not in kwargs:
                kwargs.setdefault("stderr", True)
                kwargs.setdefault("stdout", True)
            kwargs.setdefault("encoding", "utf-8")
            result = cros_build_lib.run(["ls", path], **kwargs)
            return result.stdout.splitlines()
        else:
            return [x.url for x in self.List(path, **kwargs)]

    def List(self, path, details=False, generation=False, **kwargs):
        """Does a directory listing of the given gs path.

        Args:
            path: The path to get a listing of.
            details: Whether to include size/timestamp info.
            generation: Whether to include metadata info & historical versions.
            **kwargs: See options that DoCommand takes.

        Returns:
            A list of GSListResult objects that matched |path|.  Might be more
            than one if a directory or path include wildcards/etc...
        """
        ret = []
        if self.dry_run:
            return ret

        if generation:
            details = True

        cmd = ["ls"]
        if details:
            cmd += ["-l"]
        if generation:
            cmd += ["-a"]
        cmd += ["--"]
        if isinstance(path, str):
            cmd.append(path)
        else:
            cmd.extend(path)

        # We always request the extended details as the overhead compared to a
        # plain listing is negligible.
        kwargs["stdout"] = True
        lines = self.DoCommand(cmd, **kwargs).stdout.splitlines()

        if details:
            # The last line is expected to be a summary line.  Ignore it.
            lines = lines[:-1]
            ls_re = LS_LA_RE
        else:
            ls_re = LS_RE

        # Handle optional fields.
        intify = lambda x: int(x) if x else None

        # Parse out each result and build up the results list.
        for line in lines:
            match = ls_re.search(line)
            if not match:
                raise GSContextException("unable to parse line: %s" % line)
            if match.group("creation_time"):
                timestamp = datetime.datetime.strptime(
                    match.group("creation_time"), DATETIME_FORMAT
                )
            else:
                timestamp = None

            ret.append(
                GSListResult(
                    content_length=intify(match.group("content_length")),
                    creation_time=timestamp,
                    url=match.group("url"),
                    generation=intify(match.group("generation")),
                    metageneration=intify(match.group("metageneration")),
                )
            )

        return ret

    def GetSize(self, path, **kwargs):
        """Returns size of a single object (local or GS)."""
        if not gs_urls_util.PathIsGs(path):
            return os.path.getsize(path)
        else:
            return self.Stat(path, **kwargs).content_length

    def GetCreationTime(self, path: str, **kwargs) -> datetime.datetime:
        """Returns the creation time of a single object."""
        return self.Stat(path, **kwargs).creation_time

    def GetCreationTimeSince(
        self, path: str, since_date: datetime.datetime, **kwargs
    ) -> datetime.timedelta:
        """Returns the time since since_date of a single object."""
        return since_date - self.GetCreationTime(path, **kwargs)

    def Move(self, src_path, dest_path, **kwargs):
        """Move/rename to/from GS bucket.

        Args:
            src_path: Fully qualified local path or full gs:// path of the src
                file.
            dest_path: Fully qualified local path or full gs:// path of the dest
                file.
            **kwargs: See options that DoCommand takes.
        """
        cmd = ["mv", "--", src_path, dest_path]
        return self.DoCommand(cmd, **kwargs)

    def SetACL(self, path, acl=None, **kwargs):
        """Set access on a file already in google storage.

        Args:
            path: gs:// url that will have acl applied to it.
            acl: An ACL permissions file or canned ACL.
            **kwargs: See options that DoCommand takes.
        """
        if acl is None:
            if not self.acl:
                raise GSContextException(
                    "SetAcl invoked w/out a specified acl, nor a default acl."
                )
            acl = self.acl

        cmd = ["acl", "set", "--", acl]
        if isinstance(path, str):
            cmd.append(path)
        else:
            cmd.extend(path)

        self.DoCommand(cmd, **kwargs)

    def ChangeACL(
        self, upload_url, acl_args_file=None, acl_args=None, **kwargs
    ):
        """Change access on a file already in google storage with "acl ch".

        Args:
            upload_url: gs:// url that will have acl applied to it.
            acl_args_file: A file with arguments to the gsutil acl ch command.
                The arguments can be spread across multiple lines. Comments
                start with a # character and extend to the end of the line.
                Exactly one of this argument or acl_args must be set.
            acl_args: A list of arguments for the gsutil acl ch command. Exactly
                one of this argument or acl_args must be set.
            **kwargs: See options that DoCommand takes.
        """
        if acl_args_file and acl_args:
            raise GSContextException(
                "ChangeACL invoked with both acl_args and acl_args set."
            )
        if not acl_args_file and not acl_args:
            raise GSContextException(
                "ChangeACL invoked with neither acl_args nor acl_args set."
            )

        if acl_args_file:
            lines = osutils.ReadFile(acl_args_file).splitlines()
            # Strip out comments.
            lines = [x.split("#", 1)[0].strip() for x in lines]
            acl_args = " ".join([x for x in lines if x]).split()

        # Some versions of gsutil bubble up precondition failures even when we
        # didn't request it due to how ACL changes happen internally to gsutil.
        # https://crbug.com/763450
        # We keep the retry limit a bit low because DoCommand already has its
        # own level of retries.
        retry_util.RetryException(
            GSContextPreconditionFailed,
            3,
            self.DoCommand,
            ["acl", "ch"] + acl_args + [upload_url],
            **kwargs,
        )

    def Exists(self, path, **kwargs):
        """Checks whether the given object exists.

        Args:
            path: Local path or gs:// url to check.
            **kwargs: Flags to pass to DoCommand.

        Returns:
            True if the path exists; otherwise returns False.
        """
        if not gs_urls_util.PathIsGs(path):
            return os.path.exists(path)

        try:
            self.Stat(path, **kwargs)
        except GSNoSuchKey:
            return False

        return True

    def Remove(self, path, recursive=False, ignore_missing=False, **kwargs):
        """Remove the specified file.

        Args:
            path: Full gs:// url of the file to delete.
            recursive: Remove recursively starting at path.
            ignore_missing: Whether to suppress errors about missing files.
            **kwargs: Flags to pass to DoCommand.
        """
        cmd = ["rm"]
        if "recurse" in kwargs:
            raise TypeError('"recurse" has been renamed to "recursive"')
        if recursive:
            cmd.append("-R")
        cmd.append("--")
        if isinstance(path, str):
            cmd.append(path)
        else:
            cmd.extend(path)
        try:
            self.DoCommand(cmd, **kwargs)
        except GSNoSuchKey:
            if not ignore_missing:
                raise

    def GetGeneration(self, path):
        """Get the generation and metageneration of the given |path|.

        Returns:
            A tuple of the generation and metageneration.
        """
        try:
            res = self.Stat(path)
        except GSNoSuchKey:
            return 0, 0

        return res.generation, res.metageneration

    def Stat(self, path, **kwargs):
        """Stat a GS file, and get detailed information.

        Args:
            path: A GS path for files to Stat. Wildcards are NOT supported.
            **kwargs: Flags to pass to DoCommand.

        Returns:
            A GSStatResult object with all fields populated.

        Raises:
            Assorted GSContextException exceptions.
        """
        try:
            res = self.DoCommand(["stat", "--", path], stdout=True, **kwargs)
        except GSCommandError as e:
            # Because the 'gsutil stat' command logs errors itself (instead of
            # raising errors internally like other commands), we have to look
            # for errors ourselves.  See the related bug report here:
            # https://github.com/GoogleCloudPlatform/gsutil/issues/288
            # Example lines:
            # No URLs matched gs://bucket/file
            # Some more msg: No URLs matched gs://bucket/file
            if e.stderr and any(
                x.startswith("No URLs matched") for x in e.stderr.splitlines()
            ):
                raise GSNoSuchKey("Stat Error: No URLs matched %s." % path)

            # No idea what this is, so just choke.
            raise

        # In dryrun mode, DoCommand doesn't return an object, so we need to fake
        # out the behavior ourselves.
        if self.dry_run:
            return GSStatResult(
                creation_time=datetime.datetime.now(),
                content_length=0,
                content_type="application/octet-stream",
                hash_crc32c="AAAAAA==",
                hash_md5="",
                etag="",
                generation=0,
                metageneration=0,
            )

        # We expect Stat output like the following. However, the
        # Content-Language line appears to be optional based on how the file in
        # question was created.
        #
        # gs://bucket/path/file:
        #     Creation time:      Sat, 23 Aug 2014 06:53:20 GMT
        #     Content-Language:   en
        #     Content-Length:     74
        #     Content-Type:       application/octet-stream
        #     Hash (crc32c):      BBPMPA==
        #     Hash (md5):         ms+qSYvgI9SjXn8tW/5UpQ==
        #     ETag:               CNCgocbmqMACEAE=
        #     Generation:         1408776800850000
        #     Metageneration:     1

        if not res.stdout.startswith("gs://"):
            raise GSContextException(f"Unexpected stat output: {res.stdout}")

        def _GetField(name, optional=False):
            m = re.search(r"%s:\s*(.+)" % re.escape(name), res.stdout)
            if m:
                return m.group(1)
            elif optional:
                return None
            else:
                raise GSContextException(
                    'Field "%s" missing in "%s"' % (name, res.stdout)
                )

        return GSStatResult(
            creation_time=datetime.datetime.strptime(
                _GetField("Creation time"), "%a, %d %b %Y %H:%M:%S %Z"
            ),
            content_length=int(_GetField("Content-Length")),
            content_type=_GetField("Content-Type"),
            hash_crc32c=_GetField("Hash (crc32c)"),
            hash_md5=_GetField("Hash (md5)", optional=True),
            etag=_GetField("ETag"),
            generation=int(_GetField("Generation")),
            metageneration=int(_GetField("Metageneration")),
        )

    def Counter(self, path):
        """Return a GSCounter object pointing at a |path| in Google Storage.

        Args:
            path: The path to the counter in Google Storage.
        """
        return GSCounter(self, path)

    def WaitForGsPaths(self, paths, timeout, period=10):
        """Wait until a list of files exist in GS.

        Args:
            paths: The list of files to wait for.
            timeout: Max seconds to wait for file to appear.
            period: How often to check for files while waiting.

        Raises:
            timeout_util.TimeoutError if the timeout is reached.
        """
        # Copy the list of URIs to wait for, so we don't modify the caller's
        # context.
        pending_paths = paths[:]

        def _CheckForExistence():
            pending_paths[:] = [x for x in pending_paths if not self.Exists(x)]

        def _Retry(_return_value):
            # Retry, if there are any pending paths left.
            return pending_paths

        timeout_util.WaitForSuccess(
            _Retry, _CheckForExistence, timeout=timeout, period=period
        )

    def ContainsWildcard(self, url):
        """Checks whether url_string contains a wildcard.

        Args:
            url: URL string to check.

        Returns:
            True if |url| contains a wildcard.
        """
        return bool(WILDCARD_REGEX.search(url))

    def GetGsNamesWithWait(
        self, pattern, url, timeout=600, period=10, is_regex_pattern=False
    ):
        """Returns the Google Storage names specified by the given pattern.

        This method polls Google Storage until the target files specified by the
        pattern is available or until the timeout occurs. Because we may not
        know the exact name of the target files, the method accepts a filename
        pattern, to identify whether a file whose name matches the pattern
        exists (e.g. use pattern '*_full_*' to search for the full payload
        'chromeos_R17-1413.0.0-a1_x86-mario_full_dev.bin'). Returns the name
        only if found before the timeout.

        Warning: GS listing are not perfect, and are eventually consistent.
        Doing a search for file existence is a 'best effort'. Calling code
        should be aware and ready to handle that.

        Args:
            pattern: a path pattern (glob or regex) identifying the files we
                need.
            url: URL of the Google Storage bucket.
            timeout: how many seconds are we allowed to keep trying.
            period: how many seconds to wait between attempts.
            is_regex_pattern: Whether the pattern is a regex (otherwise a glob).

        Returns:
            The list of files matching the pattern in Google Storage bucket or
            None if the files are not found and hit the
            timeout_util.TimeoutError.
        """

        def _GetGsName():
            uploaded_list = [os.path.basename(p.url) for p in self.List(url)]

            if is_regex_pattern:
                filter_re = re.compile(pattern)
                matching_names = [
                    f for f in uploaded_list if filter_re.search(f) is not None
                ]
            else:
                matching_names = fnmatch.filter(uploaded_list, pattern)

            return matching_names

        try:
            matching_names = None
            if not (is_regex_pattern or self.ContainsWildcard(pattern)):
                try:
                    self.WaitForGsPaths(["%s/%s" % (url, pattern)], timeout)
                    return [os.path.basename(pattern)]
                except GSCommandError:
                    pass

            if not matching_names:
                matching_names = timeout_util.WaitForSuccess(
                    lambda x: not x, _GetGsName, timeout=timeout, period=period
                )

            logging.debug(
                "matching_names=%s, is_regex_pattern=%r",
                matching_names,
                is_regex_pattern,
            )
            return matching_names
        except timeout_util.TimeoutError:
            return None

    def LoadKeyValueStore(
        self,
        src_uri: str,
        ignore_missing: bool = False,
        multiline: bool = False,
        acl: Optional[str] = None,
    ) -> Dict[str, str]:
        """Turn a remote key=value file from Google Storage into a dict.

        Args:
            src_uri: The full gs:// path to the key-value store file.
            ignore_missing: If True and the URI is not found, return {}.
            multiline: Allow a value enclosed by quotes to span multiple lines.
            acl: An ACL permissions file or canned ACL.

        Returns:
            A dict containing the key-values stored in the remote file.
        """
        with tempfile.NamedTemporaryFile() as f:
            self.Copy(src_uri, f.name, acl=acl)
            # NOTE: LoadFile accepts an already-open file, but we need to pass
            # `f.name` here anyway: gsutil writes to a tempfile which it
            # renames over `f.name`, so the file object that `f.fileno`
            # references is useless after `Copy` completes.
            return key_value_store.LoadFile(
                f.name, ignore_missing=ignore_missing, multiline=multiline
            )


def _FirstMatch(predicate, elems):
    """Returns the first element matching the given |predicate|.

    Args:
        predicate: A function which takes an element and returns a bool
        elems: A sequence of elements.
    """
    matches = [x for x in elems if predicate(x)]
    return matches[0] if matches else None


def _FirstSubstring(superstring, haystack):
    """Return the first elem of |haystack|, a substring of |superstring|.

    Args:
        superstring: A string to search for substrings of.
        haystack: A sequence of strings to search through.
    """
    return _FirstMatch(lambda s: s in superstring, haystack)


@contextlib.contextmanager
def TemporaryURL(prefix):
    """Context manager to generate a random URL.

    At the end, the URL will be deleted.
    """
    url = "%s/chromite-temp/%s/%s/%s" % (
        constants.TRASH_BUCKET,
        prefix,
        getpass.getuser(),
        cros_build_lib.GetRandomString(),
    )
    ctx = GSContext()
    ctx.Remove(url, ignore_missing=True, recursive=True)
    try:
        yield url
    finally:
        ctx.Remove(url, ignore_missing=True, recursive=True)
