# Copyright 2013 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Hold the functions that do the real work generating payloads."""

import base64
import collections
import datetime
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from typing import List, Optional, Union

from chromite.api.gen.chromite.api import payload_pb2
from chromite.lib import cgpt
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import dlc_lib
from chromite.lib import image_lib
from chromite.lib import osutils
from chromite.lib import path_util
from chromite.lib.paygen import download_cache
from chromite.lib.paygen import filelib
from chromite.lib.paygen import gspaths
from chromite.lib.paygen import partition_lib
from chromite.lib.paygen import signer_payloads_client
from chromite.lib.paygen import urilib
from chromite.lib.paygen import utils
from chromite.scripts import cros_set_lsb_release
from chromite.utils import pformat


DESCRIPTION_FILE_VERSION = 2

# See class docs for functionality information. Configured to reserve 6GB and
# consider each individual task as consuming 6GB. Therefore we won't start a
# new task unless available memory is about 12GB (including base utilization).
# We set a total max concurrency as a precaution. TODO(crbug.com/1016555)
_mem_semaphore = utils.MemoryConsumptionSemaphore(
    system_available_buffer_bytes=2**31 + 2**32,  # 6 GB
    single_proc_max_bytes=2**31 + 2**32,  # 6 GB
    quiescence_time_seconds=60.0,
    total_max=10,
    unchecked_acquires=4,
)


class Error(Exception):
    """Base class for payload generation errors."""


class UnexpectedSignerResultsError(Error):
    """This is raised when signer results don't match our expectations."""


class PayloadVerificationError(Error):
    """Raised when the generated payload fails to verify."""


class PayloadGenerationSkippedException(Exception):
    """Base class for reasons that payload generation might be skipped.

    Note that sometimes this is not an error (and thus doesn't inherit from
    Error). Callers might deliberately try to generate an impossible payload,
    such as generating a miniOS payload for an image without a miniOS partition,
    because that is faster than checking whether an image is miniOS-compatible
    and then generating the payload.
    """


class MiniOSException(PayloadGenerationSkippedException):
    """Base class for MiniOS-related exceptions."""

    def return_code(self) -> int:
        """Return code to use in a PayloadService.GenerationResponse.

        When attempting to generate a miniOS payload, if we failed to generate,
        it is helpful to explain what happened. Subclasses should override this
        method to specify the failure reason.
        """
        return payload_pb2.GenerationResponse.UNSPECIFIED


class NoMiniOSPartitionException(MiniOSException):
    """When generating a miniOS payload for an img with no miniOS part."""

    def return_code(self) -> int:
        """Failure reason indicating that the image is not miniOS-compatible."""
        return payload_pb2.GenerationResponse.NOT_MINIOS_COMPATIBLE


class MiniOSPartitionMismatchException(MiniOSException):
    """When there is a mismatch in recovery key count for source and target."""

    def return_code(self) -> int:
        """Failure reason indicating a mismatch in recovery keys."""
        return payload_pb2.GenerationResponse.MINIOS_COUNT_MISMATCH


class PaygenSigner:
    """Class to manager the payload signer."""

    def __init__(
        self,
        chroot: chroot_lib.Chroot,
        work_dir,
        private_key=None,
        payload_build=None,
        local_signing=False,
        docker_image=None,
    ):
        """Initializer.

        Args:
            chroot: Chroot to work with.
            work_dir: A working directory inside the chroot.
            private_key: The private keys to sign the payload with.
            payload_build: The build defined for the payload.
            local_signing: Use the new local signing prototype.
            docker_image: Docker image to use for local signing.
        """
        self.public_key = None

        self._chroot = chroot
        self._work_dir = work_dir
        self._private_key = private_key
        self._payload_build = payload_build
        self._local_signing = local_signing
        self._docker_image = docker_image

        self._signer = None
        self._Initialize()

    def _Initialize(self):
        """Initializes based on which bucket the payload is supposed to go."""
        if self._local_signing:
            logging.info("Using local signer (prototype).")
            self._signer = signer_payloads_client.LocalSignerPayloadsClient(
                self._docker_image, self._payload_build, self._work_dir
            )

            # We set the private key to None, so we don't accidentally use a
            # valid passed private key to verify the image.
            if self._private_key:
                logging.warning(
                    "A private key should not be passed for official builds."
                )
            self._private_key = None
        else:
            if (
                self._payload_build
                and self._payload_build.bucket
                == gspaths.ChromeosReleases.BUCKET
            ):
                logging.info("Using GCS signer.")
                # Using the official buckets, so sign it with official signers.
                self._signer = (
                    signer_payloads_client.SignerPayloadsClientGoogleStorage(
                        self._chroot, self._payload_build, self._work_dir
                    )
                )
                # We set the private key to None, so we don't accidentally use a
                # valid passed private key to verify the image.
                if self._private_key:
                    logging.warning(
                        "A private key should not be passed for official "
                        "builds."
                    )
                self._private_key = None
            else:
                logging.info("Using local private key.")
                # Otherwise use a private key for signing and verifying the
                # payload. If no private_key was provided, use a test key.
                if not self._private_key:
                    self._private_key = (
                        constants.CHROMITE_DIR / "ssh_keys" / "testing_rsa"
                    )
                self._signer = (
                    signer_payloads_client.UnofficialSignerPayloadsClient(
                        self._chroot, self._private_key, self._work_dir
                    )
                )

            if self._private_key and self._signer:
                self.public_key = os.path.join(self._work_dir, "public_key.pem")
                self._signer.ExtractPublicKey(self.public_key)

    def GetHashSignatures(self, *args, **kwargs):
        """Wrapper to forward into signer."""
        return self._signer.GetHashSignatures(*args, **kwargs)


class PaygenPayload:
    """Class to manage the process of generating and signing a payload."""

    # 250 GB of cache.
    CACHE_SIZE = 250 * 1024 * 1024 * 1024

    # 10 minutes.
    _SEMAPHORE_TIMEOUT = 10 * 60

    # What keys do we sign payloads with, and what size are they?
    PAYLOAD_SIGNATURE_KEYSETS = ("update_signer",)
    PAYLOAD_SIGNATURE_SIZES_BYTES = (2048 // 8,)  # aka 2048 bits in bytes.

    TEST_IMAGE_NAME = "chromiumos_test_image.bin"
    RECOVERY_IMAGE_NAME = "recovery_image.bin"
    BASE_IMAGE_NAME = "chromiumos_base_image.bin"

    _KERNEL = "kernel"
    _ROOTFS = "root"
    _MINIOS = "minios"

    def __init__(
        self,
        chroot: chroot_lib.Chroot,
        payload: gspaths.Payload,
        work_dir: Union[str, os.PathLike],
        signer: Optional[PaygenSigner] = None,
        verify: bool = False,
        upload: bool = True,
        cache_dir: Optional[Union[str, os.PathLike]] = None,
        static: bool = True,
    ):
        """Init for PaygenPayload.

        Args:
            chroot: Chroot to work with.
            payload: An instance of gspaths.Payload describing the payload to
                generate.
            work_dir: A working directory inside the chroot to put temporary
                files. This can NOT be shared among different runs of
                PaygenPayload otherwise there would be file collisions. Among
                the things that may go into this directory are intermediate
                image files, extracted partitions, different logs and metadata
                files, the payload itself, postinstall config file, etc.
            signer: PaygenSigner if payload should be signed, otherwise None.
            verify: whether the payload should be verified after being generated
            upload: Boolean saying if payload generation results should be
                uploaded.
            cache_dir: If passed, override the default cache dir (useful on
                bots).
            static: Static local file and upload URI names otherwise random
                string is added into the file/URI names.
        """
        self.chroot = chroot
        self.payload = payload
        self.work_dir = work_dir
        self._verify = verify
        self._minor_version = None
        self._upload = upload
        self.static = static

        self.partition_names = None
        self.tgt_partitions = None
        self.src_partitions = None

        # Define properties here to avoid linter warnings.
        self.metadata_size = 0
        self.tgt_image_file = None
        self.src_image_file = None

        self._appid = ""

        # Make linter happy.
        self._SetupNewFileNames()

        # How big will the signatures be.
        self._signature_sizes = [
            str(size) for size in self.PAYLOAD_SIGNATURE_SIZES_BYTES
        ]
        self.signer = signer

        # This cache dir will be shared with other processes, but we need our
        # own instance of the cache manager to properly coordinate.
        cache_dir = cache_dir or self._FindCacheDir()
        self._cache = download_cache.DownloadCache(
            cache_dir, cache_size=PaygenPayload.CACHE_SIZE
        )

    def _SetupNewFileNames(self):
        """Initializes files with static names or with random suffixes."""
        self.rand = not self.static or self.payload.minios
        rand = f"-{cros_build_lib.GetRandomString()}" if self.rand else ""

        self.src_image_file = os.path.join(
            self.work_dir, f"src_image{rand}.bin"
        )
        self.tgt_image_file = os.path.join(
            self.work_dir, f"tgt_image{rand}.bin"
        )

        self.payload_file = os.path.join(self.work_dir, f"delta{rand}.bin")
        self.log_file = os.path.join(self.work_dir, f"delta{rand}.log")
        self.description_file = os.path.join(self.work_dir, f"delta{rand}.json")

        self.metadata_size = 0
        self.metadata_hash_file = os.path.join(
            self.work_dir, f"metadata_hash{rand}"
        )
        self.payload_hash_file = os.path.join(
            self.work_dir, f"payload_hash{rand}"
        )

        self._postinst_config_file = os.path.join(
            self.work_dir, f"postinst_config{rand}"
        )

        self.signed_payload_file = self.payload_file + ".signed"
        self.metadata_signature_file = self._MetadataUri(
            self.signed_payload_file
        )

    def _MetadataUri(self, uri):
        """Given a payload uri, find the uri for the metadata signature."""
        return uri + ".metadata-signature"

    def _LogsUri(self, uri):
        """Given a payload uri, find the uri for the logs."""
        return uri + ".log"

    def _JsonUri(self, uri):
        """Given a payload uri, find the json payload description uri."""
        return uri + ".json"

    def _FindCacheDir(self):
        """Helper for deciding what cache directory to use.

        Returns:
            Returns a directory suitable for use with a DownloadCache.
        """
        return os.path.join(path_util.GetCacheDir(), "paygen_cache")

    def _GetDlcImageParams(self, tgt_image, src_image=None):
        """Returns parameters related to target and source DLC images.

        Args:
            tgt_image: The target image.
            src_image: The source image.

        Returns:
            A tuple of three parameters that was discovered from the image: The
            DLC ID, The DLC package and its release AppID.
        """

        def _GetImageParams(image):
            """Returns the parameters of a single DLC image.

            Args:
                image: The input image.

            Returns:
                Same values as _GetDlcImageParams()
            """
            mount_point = os.path.join(self.work_dir, "mount-point")
            osutils.MountDir(image, mount_point, mount_opts=("ro",))
            try:
                lsb_release = utils.ReadLsbRelease(mount_point)
            finally:
                osutils.UmountDir(mount_point)

            dlc_id = lsb_release[dlc_lib.DLC_ID_KEY]
            dlc_package = lsb_release[dlc_lib.DLC_PACKAGE_KEY]
            appid = lsb_release[dlc_lib.DLC_APPID_KEY]

            if gspaths.IsDLCImage(image):
                if dlc_id != image.dlc_id:
                    raise Error(
                        "The DLC ID (%s) inferred from the file path does not "
                        "match the one (%s) from the lsb-release."
                        % (image.dlc_id, dlc_id)
                    )
                if dlc_package != image.dlc_package:
                    raise Error(
                        "The DLC package (%s) inferred from the file path "
                        "does not match the one (%s) from the lsb-release."
                        % (image.dlc_package, dlc_package)
                    )

            return dlc_id, dlc_package, appid

        tgt_dlc_id, tgt_dlc_package, tgt_appid = _GetImageParams(tgt_image)
        if src_image:
            src_dlc_id, src_dlc_package, src_appid = _GetImageParams(src_image)
            if tgt_dlc_id != src_dlc_id:
                raise Error(
                    "Source (%s) and target (%s) DLC IDs do not match."
                    % (src_dlc_id, tgt_dlc_id)
                )
            if tgt_dlc_package != src_dlc_package:
                raise Error(
                    "Source (%s) and target (%s) DLC packages do not match."
                    % (src_dlc_package, tgt_dlc_package)
                )
            if tgt_appid != src_appid:
                logging.warning(
                    "Source (%s) and target (%s) App IDs do not match.",
                    src_appid,
                    tgt_appid,
                )

        return tgt_dlc_id, tgt_dlc_package, tgt_appid

    def _GetPlatformImageParams(self, image):
        """Returns parameters related to target or source platform images.

        Since this function is mounting a GPT image, if the mount (for reasons
        like a bug, etc.), changes the bits on the image, then the image cannot
        be trusted after this call.

        Args:
            image: The input image.

        Returns:
            The release APPID of the image and the minor version.
        """
        # Mount the ROOT-A partition of the image. The reason we don't mount the
        # extracted partition directly is that if by mistake/bug the mount
        # changes the bits on the partition, then we will create a payload for a
        # changed partition which is not equivalent to the original partition.
        # So just mount the partition of the GPT image and even if it changes,
        # then who cares.
        #
        # TODO(crbug.com/925203): Replace this with
        #   image_lib.LoopbackPartition() once the mentioned bug is resolved.
        with osutils.TempDir(base_dir=self.work_dir) as mount_point:
            with image_lib.LoopbackPartitions(
                image,
                destination=mount_point,
                part_ids=(constants.PART_ROOT_A,),
            ):
                sysroot_dir = os.path.join(
                    mount_point, "dir-%s" % constants.PART_ROOT_A
                )
                lsb_release = utils.ReadLsbRelease(sysroot_dir)
                app_id = lsb_release.get(
                    cros_set_lsb_release.LSB_KEY_APPID_RELEASE
                )
                if app_id is None:
                    board = lsb_release.get(
                        cros_set_lsb_release.LSB_KEY_APPID_BOARD
                    )
                    logging.error(
                        "APPID is missing in board %s. In some boards that do "
                        "not do auto updates, like amd64-generic, this is "
                        "expected, otherwise this is an error.",
                        board,
                    )
                minor_version = None
                if self.payload.minios:
                    # Update APPID for miniOS partition.
                    if app_id:
                        app_id += "_minios"
                        logging.debug(
                            "APPID for miniOS partition is %s", app_id
                        )
                    if self.payload.src_image:
                        # Get minor version for delta miniOS payloads.
                        minor_version = utils.ReadMinorVersion(sysroot_dir)
                        if not minor_version:
                            raise Error(
                                "Unable to extract minor version from source "
                                "image"
                            )
                        logging.info(
                            "Minor version extracted from source: %s",
                            minor_version,
                        )
                return app_id, minor_version

    def _MaybeSkipPayloadGeneration(self) -> None:
        """Raises an exception if paygen should be skipped for some reason.

        Raises:
            MiniOSException: If the payload could not be generated due to a
                miniOS issue (such as the image having no miniOS partition).
        """
        if self.payload.minios:
            try:
                self._CheckEitherImageIsMissingMiniOSPayload()
            except (Error, cgpt.Error) as e:
                logging.warning(
                    "Caught exception checking whether images have miniOS "
                    "parts: %s",
                    e,
                )

    def _CheckEitherImageIsMissingMiniOSPayload(self):
        """Determines whether the source or target image has no miniOS parts.

        If this is a full payload, then there is no src image. In that case,
        only the tgt image will be evaluated.

        Raises:
            MiniOSException: If either the source or target image is missing
                a miniOS partition, or if some other issue arose while checking
                for a miniOS partition.
        """
        try:
            self._CheckImageHasMiniOSPartition(self.tgt_image_file)
        except:
            logging.info("Target missing miniOS partition")
            raise
        if self.payload.src_image:
            self._CheckImageHasMiniOSPartition(self.src_image_file)

    def _CheckImageHasMiniOSPartition(self, image_file):
        """Checks whether the given image has a miniOS partition.

        Args:
            image_file: Local path to the image file.

        Raises:
            MiniOSPartitionMismatchException: If there is a mismatch in the
                recovery key count for the source and target images.
            NoMiniOSPartitionException: If there is no miniOS partition for this
                image.
        """
        disk = cgpt.Disk.FromImage(image_file, chroot=self.chroot)
        try:
            parts = disk.GetPartitionByTypeGuid(cgpt.MINIOS_TYPE_GUID)
        except KeyError:
            raise NoMiniOSPartitionException
        # These are hard enforcements on miniOS partitions now to avoid
        # payload generation when either A || B partitions aren't set.
        if len(parts) != 2:
            logging.info("MiniOS partition count did not match.")
            raise MiniOSPartitionMismatchException

    def _PreparePartitions(self, part_a: bool = True):
        """Prepares parameters related to partitions of the given image.

        This function basically distinguishes between normal platform images and
        DLC images and creates and checks parameters necessary for each of them.

        Args:
            part_a: True to extract default/A partition.
        """
        tgt_image_type = partition_lib.LookupImageType(self.tgt_image_file)
        if self.payload.src_image:
            src_image_type = partition_lib.LookupImageType(self.src_image_file)
            if (
                tgt_image_type != src_image_type
                and partition_lib.CROS_IMAGE in (tgt_image_type, src_image_type)
            ):
                raise Error(
                    "Source (%s) and target (%s) images have different types."
                    % (src_image_type, tgt_image_type)
                )

        if tgt_image_type == partition_lib.DLC_IMAGE:
            logging.info("Detected a DLC image.")

            # DLC module image has only one partition which is the image itself.
            dlc_id, dlc_package, self._appid = self._GetDlcImageParams(
                self.tgt_image_file,
                src_image=self.src_image_file
                if self.payload.src_image
                else None,
            )
            self.partition_names = ("dlc/%s/%s" % (dlc_id, dlc_package),)
            self.tgt_partitions = (self.tgt_image_file,)
            self.src_partitions = (self.src_image_file,)

        elif tgt_image_type == partition_lib.CROS_IMAGE:
            logging.info("Detected a Chromium OS image.")
            if self.payload.minios:
                logging.info("Extracting the MINIOS partition.")
                self.partition_names = (self._MINIOS,)
                self._GetPartitionFiles()
                partition_lib.ExtractMiniOS(
                    self.tgt_image_file, self.tgt_partitions[0], part_a=part_a
                )
                if self.payload.src_image:
                    partition_lib.ExtractMiniOS(
                        self.src_image_file,
                        self.src_partitions[0],
                        part_a=part_a,
                    )
            else:
                self.partition_names = (self._ROOTFS, self._KERNEL)
                self._GetPartitionFiles()
                partition_lib.ExtractRoot(
                    self.tgt_image_file, self.tgt_partitions[0]
                )
                partition_lib.ExtractKernel(
                    self.tgt_image_file, self.tgt_partitions[1]
                )
                if self.payload.src_image:
                    partition_lib.ExtractRoot(
                        self.src_image_file, self.src_partitions[0]
                    )
                    partition_lib.ExtractKernel(
                        self.src_image_file, self.src_partitions[1]
                    )
                # Makes sure we have generated postinstall config for major
                # version 2 and platform image.
                self._GeneratePostinstConfig(True)

            # This step should be done after extracting partitions, look at the
            # _GetPlatformImageParams() documentation for more info.
            if self.payload.src_image:
                self._appid, self._minor_version = self._GetPlatformImageParams(
                    self.src_image_file
                )
            else:
                # Full payloads do not need the minor version and should use the
                # target image.
                self._appid, _ = self._GetPlatformImageParams(
                    self.tgt_image_file
                )

            # Reset the target image file path so no one uses it later.
            self.tgt_image_file = None

        else:
            raise Error("Invalid image type %s" % tgt_image_type)

    def _GetPartitionFiles(self):
        """Creates the target and source file paths for each partition."""
        self.tgt_partitions = tuple(
            os.path.join(self.work_dir, "tgt_%s.bin" % name)
            for name in self.partition_names
        )
        self.src_partitions = tuple(
            os.path.join(self.work_dir, "src_%s.bin" % name)
            for name in self.partition_names
        )

    def _RunGeneratorCmd(self, cmd, squawk_wrap=False):
        """Wrapper for run in chroot.

        Run the given command inside the chroot. It will automatically log the
        command output. Note that the command's stdout and stderr are combined
        into a single string.

        For context on why this is so complex see: crbug.com/1035799

        Args:
            cmd: Program and argument list in a list.
                ['delta_generator', '--help']
            squawk_wrap: Optionally run the cros_build_lib command in a thread
                to avoid being killed by the ProcessSilentTimeout during quiet
                periods of delta_gen.

        Raises:
            cros_build_lib.RunCommandError if the command did not succeed.
        """
        response_queue = collections.deque()

        # The later thread's start() function.
        def _inner_run(cmd, response_queue):
            try:
                # Run the command.
                result = self.chroot.run(
                    cmd,
                    stdout=True,
                    stderr=subprocess.STDOUT,
                )
                response_queue.append(result)
            except cros_build_lib.RunCommandError as e:
                response_queue.append(e)

        if squawk_wrap:
            inner_run_thread = threading.Thread(
                target=_inner_run,
                name="delta_generator_run_wrapper",
                args=(cmd, response_queue),
            )
            inner_run_thread.setDaemon(True)
            inner_run_thread.start()
            # Wait for the inner run thread to finish, waking up each second.
            i = 1
            while inner_run_thread.is_alive():
                i += 1
                time.sleep(1)
                # Only report once an hour, otherwise we'd be too noisy.
                if i % 3600 == 0:
                    logging.info("Placating ProcessSilentTimeout...")
        else:
            _inner_run(cmd, response_queue)

        try:
            result = response_queue.pop()
            if isinstance(result, cros_build_lib.RunCommandError):
                # Dump error output and re-raise the exception.
                logging.error(
                    "Nonzero exit code (%d), dumping command output:\n%s",
                    result.returncode,
                    result.stdout,
                )
                raise result
            elif isinstance(result, cros_build_lib.CompletedProcess):
                self._StoreLog("Output of command: " + result.cmdstr)
                self._StoreLog(result.stdout.decode("utf-8", "replace"))
            else:
                raise cros_build_lib.RunCommandError(
                    "return type from _inner_run unknown"
                )
        except IndexError:
            raise cros_build_lib.RunCommandError(
                "delta_generator_run_wrapper did not return a value"
            )

    @staticmethod
    def _BuildArg(flag, dict_obj, key, default=None):
        """Return a command-line argument if its value is present in |dict_obj|.

        Args:
            flag: the flag name to use with the argument value, e.g. --foo; if
                None or an empty string, no flag will be used.
            dict_obj: A dictionary mapping possible keys to values.
            key: The key of interest; e.g. 'foo'.
            default: Optional default value to use if key is not in dict_obj.

        Returns:
            If dict_obj[key] contains a non-False value or default is non-False,
            returns a string representing the flag and value arguments (e.g.
            '--foo=bar')
        """
        val = dict_obj.get(key) or default
        return "%s=%s" % (flag, str(val))

    def _PrepareImage(self, image, image_file):
        """Download and prepare an image for delta generation.

        Preparation includes downloading, extracting and converting the image
        into an on-disk format, as necessary.

        Args:
            image: an object representing the image we're processing, either
                UnsignedImageArchive or Image type from gspaths module.
            image_file: file into which the prepared image should be copied.
        """

        logging.info("Preparing image from %s as %s", image.uri, image_file)

        # Figure out what we're downloading and how to handle it.
        image_handling_by_type = {
            "signed": (None, True),
            "test": (self.TEST_IMAGE_NAME, False),
            "recovery": (self.RECOVERY_IMAGE_NAME, True),
            "base": (self.BASE_IMAGE_NAME, True),
        }
        if gspaths.IsImage(image):
            # No need to extract.
            extract_file = None
        elif gspaths.IsUnsignedImageArchive(image):
            extract_file, _ = image_handling_by_type[
                image.get("image_type", "signed")
            ]
        else:
            raise Error("Unknown image type %s" % type(image))

        # Are we downloading an archive that contains the image?
        if extract_file:
            # Archive will be downloaded to a temporary location.
            with tempfile.NamedTemporaryFile(
                prefix="image-archive-",
                suffix=".tar.xz",
                dir=self.work_dir,
                delete=False,
            ) as temp_file:
                download_file = temp_file.name
        else:
            download_file = image_file

        # Download the image file or archive. If it was just a local file,
        # ignore caching and do a simple copy. TODO(crbug.com/926034): Add a
        # caching mechanism for local files.
        if urilib.GetUriType(image.uri) == urilib.TYPE_LOCAL:
            filelib.Copy(image.uri, download_file)
        else:
            self._cache.GetFileCopy(image.uri, download_file)

        # If we downloaded an archive, extract the image file from it.
        if extract_file:
            cros_build_lib.ExtractTarball(
                download_file, self.work_dir, files_to_extract=[extract_file]
            )

            # Rename it into the desired image name.
            shutil.move(os.path.join(self.work_dir, extract_file), image_file)

            # It should be safe to delete the archive at this point.
            # TODO(crbug/1016555): consider removing the logging once resolved.
            logging.info("Removing %s", download_file)
            os.remove(download_file)

    def _GeneratePostinstConfig(self, run_postinst):
        """Generates the postinstall config file

        This file is used in update engine's major version 2.

        Args:
            run_postinst: Whether the updater should run postinst or not.
        """
        # In major version 2 we need to explicitly mark the postinst on the root
        # partition to run.
        osutils.WriteFile(
            self._postinst_config_file,
            "RUN_POSTINSTALL_root=%s\n" % ("true" if run_postinst else "false"),
        )

    def _GenerateUnsignedPayload(self):
        """Generate the unsigned delta into self.payload_file."""
        # Note that the command run here requires sudo access.
        logging.info("Generating unsigned payload as %s", self.payload_file)

        cmd = [
            "delta_generator",
            "--major_version=2",
            "--out_file=" + self.chroot.chroot_path(self.payload_file),
            # Target image args: (The order of partitions are important.)
            "--partition_names=" + ":".join(self.partition_names),
            "--new_partitions="
            + ":".join(self.chroot.chroot_path(x) for x in self.tgt_partitions),
        ]

        if os.path.exists(self._postinst_config_file):
            cmd += [
                "--new_postinstall_config_file="
                + self.chroot.chroot_path(self._postinst_config_file)
            ]

        if self.payload.src_image:
            cmd += [
                "--old_partitions="
                + ":".join(
                    self.chroot.chroot_path(x) for x in self.src_partitions
                )
            ]

        if self.payload.minios and self._minor_version:
            cmd += ["--minor_version=" + self._minor_version]

        # This can take a very long time with no output, so wrap the call.
        self._RunGeneratorCmd(cmd, squawk_wrap=True)

    def _GenerateHashes(self):
        """Generate a payload hash and a metadata hash.

        Works from an unsigned update payload.

        Returns:
            Tuple of (payload_hash, metadata_hash) as bytes.
        """
        logging.info("Calculating hashes on %s.", self.payload_file)

        cmd = [
            "delta_generator",
            "--in_file=" + self.chroot.chroot_path(self.payload_file),
            "--signature_size=" + ":".join(self._signature_sizes),
            "--out_hash_file="
            + self.chroot.chroot_path(self.payload_hash_file),
            "--out_metadata_hash_file="
            + self.chroot.chroot_path(self.metadata_hash_file),
        ]

        self._RunGeneratorCmd(cmd)

        return (
            osutils.ReadFile(self.payload_hash_file, mode="rb"),
            osutils.ReadFile(self.metadata_hash_file, mode="rb"),
        )

    def _GenerateSignerResultsError(self, format_str, *args):
        """Helper for reporting errors with signer results."""
        msg = format_str % args
        logging.error(msg)
        raise UnexpectedSignerResultsError(msg)

    def _SignHashes(self, hashes):
        """Get the signer to sign the hashes with the update payload key via GS.

        May sign each hash with more than one key, based on how many keysets are
        required.

        Args:
            hashes: List of hashes (as bytes) to be signed.

        Returns:
            List of lists which contain each signed hash (as bytes).
            [[hash_1_sig_1, hash_1_sig_2], [hash_2_sig_1, hash_2_sig_2]]
        """
        keysets = self.PAYLOAD_SIGNATURE_KEYSETS
        logging.info("Signing payload hashes with %s.", ", ".join(keysets))

        # Results look like:
        #  [[hash_1_sig_1, hash_1_sig_2], [hash_2_sig_1, hash_2_sig_2]]
        hashes_sigs = self.signer.GetHashSignatures(hashes, keysets=keysets)
        logging.info(
            "Signatures for hashes=%s and keysets=%s is %s",
            hashes,
            keysets,
            hashes_sigs,
        )

        if hashes_sigs is None:
            self._GenerateSignerResultsError("Signing of hashes failed")
        if len(hashes_sigs) != len(hashes):
            self._GenerateSignerResultsError(
                "Count of hashes signed (%d) != Count of hashes (%d).",
                len(hashes_sigs),
                len(hashes),
            )

        # Verify the results we get back the expected number of signatures.
        for hash_sigs in hashes_sigs:
            # Make sure each hash has the right number of signatures.
            if len(hash_sigs) != len(self.PAYLOAD_SIGNATURE_SIZES_BYTES):
                self._GenerateSignerResultsError(
                    "Signature count (%d) != Expected signature count (%d)",
                    len(hash_sigs),
                    len(self.PAYLOAD_SIGNATURE_SIZES_BYTES),
                )

            # Make sure each hash signature is the expected size.
            for sig, sig_size in zip(
                hash_sigs, self.PAYLOAD_SIGNATURE_SIZES_BYTES
            ):
                if len(sig) != sig_size:
                    self._GenerateSignerResultsError(
                        "Signature size (%d) != expected size(%d)",
                        len(sig),
                        sig_size,
                    )

        return hashes_sigs

    def _WriteSignaturesToFile(self, signatures):
        """Write each signature into a temp file in the chroot.

        Args:
            signatures: A list of signatures as bytes to write into file.

        Returns:
            The list of files in the chroot with the same order as signatures.
        """
        file_paths = []
        for signature in signatures:
            # TODO(b/236161656): Fix.
            # pylint: disable-next=consider-using-with
            path = tempfile.NamedTemporaryFile(
                dir=self.work_dir, delete=False
            ).name
            osutils.WriteFile(path, signature, mode="wb")
            file_paths.append(self.chroot.chroot_path(path))

        return file_paths

    def _InsertSignaturesIntoPayload(
        self, payload_signatures, metadata_signatures
    ):
        """Put payload and metadata signatures into the payload we sign.

        Args:
            payload_signatures: List of signatures as bytes for the payload.
            metadata_signatures: List of signatures as bytes for the metadata.
        """
        logging.info(
            "Inserting payload and metadata signatures into %s.",
            self.signed_payload_file,
        )

        payload_signature_file_names = self._WriteSignaturesToFile(
            payload_signatures
        )
        metadata_signature_file_names = self._WriteSignaturesToFile(
            metadata_signatures
        )

        cmd = [
            "delta_generator",
            "--in_file=" + self.chroot.chroot_path(self.payload_file),
            "--signature_size=" + ":".join(self._signature_sizes),
            "--payload_signature_file="
            + ":".join(payload_signature_file_names),
            "--metadata_signature_file="
            + ":".join(metadata_signature_file_names),
            "--out_file=" + self.chroot.chroot_path(self.signed_payload_file),
        ]

        self._RunGeneratorCmd(cmd)

    def _StoreMetadataSignatures(self, signatures):
        """Store metadata signatures related to the payload.

        Our current format for saving metadata signatures only supports a single
        signature at this time.

        Args:
            signatures: A list of metadata signatures in binary string format.
        """
        if len(signatures) != 1:
            self._GenerateSignerResultsError(
                "Received %d metadata signatures, only a single signature "
                "supported.",
                len(signatures),
            )

        logging.info(
            "Saving metadata signatures in %s.", self.metadata_signature_file
        )

        encoded_signature = base64.b64encode(signatures[0])

        with open(self.metadata_signature_file, "w+b") as f:
            f.write(encoded_signature)

    def GetPayloadPropertiesMap(self, payload_path):
        """Returns the payload's properties attributes in dictionary.

        The payload description contains a dictionary of key/values describing
        the characteristics of the payload. Look at
        update_engine/payload_generator/payload_properties.cc for the basic
        description of these values.

        In addition, we add the following three keys to description file:

        "appid": The APP ID associated with this payload.
        "public_key": The public key the payload was signed with.

        Args:
            payload_path: The path to the payload file.

        Returns:
            A map of payload properties that can be directly used to create the
            payload.json file.
        """
        try:
            payload_path = self.chroot.chroot_path(payload_path)
        except ValueError:
            # Copy the payload inside the chroot and try with that path instead.
            logging.info(
                "The payload is not in the chroot. We will copy it there in "
                "order to get its properties."
            )
            copied_payload = os.path.join(self.work_dir, "copied-payload.bin")
            shutil.copyfile(payload_path, copied_payload)
            payload_path = self.chroot.chroot_path(copied_payload)

        props_file = os.path.join(self.work_dir, "properties.json")
        cmd = [
            "delta_generator",
            "--in_file=" + payload_path,
            "--properties_file=" + self.chroot.chroot_path(props_file),
            "--properties_format=json",
        ]
        self._RunGeneratorCmd(cmd)
        with open(props_file, "rb") as f:
            props_map = json.load(f)

        # delta_generator assigns empty string for signatures when the payload
        # is not signed. Replace it with 'None' so the json.dumps() writes
        # 'null' as the value to be consistent with the current scheme and not
        # break GE.
        key = "metadata_signature"
        if not props_map[key]:
            props_map[key] = None

        props_map["appid"] = self._appid

        if self.payload.tgt_image.image_version:
            props_map['target_version'] = self.payload.tgt_image.image_version
        else:
            props_map["target_version"] = "99999.0.0"

        if self.payload.src_image:
            if self.payload.src_image.build:
                props_map[
                    "source_version"
                ] = self.payload.src_image.build.version
            else:
                props_map["source_version"] = ""

        # Add the public key if it exists.
        if self.signer and self.signer.public_key:
            props_map["public_key"] = base64.b64encode(
                osutils.ReadFile(self.signer.public_key, mode="rb")
            ).decode("utf-8")

        # We need the metadata size later for payload verification. Just grab it
        # from the properties file.
        self.metadata_size = props_map["metadata_size"]

        return props_map

    def _StorePayloadJson(self, metadata_signatures):
        """Generate the payload description json file.

        Args:
            metadata_signatures: A list of signatures in binary string format.
        """
        # Decide if we use the signed or unsigned payload file.
        payload_file = self.payload_file
        if self.signer:
            payload_file = self.signed_payload_file

        # Currently we have no way of getting the appid from the payload itself.
        # So just put what we got from the image itself (if any).
        props_map = self.GetPayloadPropertiesMap(payload_file)

        # Check that the calculated metadata signature is the same as the one on
        # the payload.
        if metadata_signatures:
            if len(metadata_signatures) != 1:
                self._GenerateSignerResultsError(
                    "Received %d metadata signatures, only one supported.",
                    len(metadata_signatures),
                )
            metadata_signature = base64.b64encode(
                metadata_signatures[0]
            ).decode("utf-8")
            if metadata_signature != props_map["metadata_signature"]:
                raise Error(
                    "Calculated metadata signature (%s) and the signature in"
                    " the payload (%s) do not match."
                    % (metadata_signature, props_map["metadata_signature"])
                )

        # Convert to Json & write out the results.
        pformat.json(props_map, fp=self.description_file, compact=True)

    def _StoreLog(self, log):
        """Store any log related to the payload.

        Write out the log to a known file name. Mostly in its own function
        to simplify unittest mocks.

        Args:
            log: The delta logs as a single string.
        """
        try:
            osutils.WriteFile(self.log_file, log, mode="a")
        except TypeError as e:
            logging.error("crbug.com/1023497 osutils.WriteFile failed: %s", e)
            logging.error("log (type %s): %r", type(log), log)
            flat = cros_build_lib.iflatten_instance(log)
            logging.error("flattened: %r", flat)
            logging.error("expanded: %r", list(flat))

    def _SignPayload(self):
        """Wrap all the steps for signing an existing payload.

        Returns:
            List of payload signatures, List of metadata signatures.
        """
        # Create hashes to sign or even if signing not needed.
        # TODO(ahassani): In practice we don't need to generate hashes if we are
        #   not signing, so when devserver stopped depending on
        #   cros_generate_update_payload. this can be reverted.
        payload_hash, metadata_hash = self._GenerateHashes()

        if not self.signer:
            return (None, None)

        # Sign them.
        # pylint: disable=unpacking-non-sequence
        payload_signatures, metadata_signatures = self._SignHashes(
            [payload_hash, metadata_hash]
        )
        # pylint: enable=unpacking-non-sequence

        # Insert payload and metadata signature(s).
        self._InsertSignaturesIntoPayload(
            payload_signatures, metadata_signatures
        )

        # Store metadata signature(s).
        self._StoreMetadataSignatures(metadata_signatures)

        return (payload_signatures, metadata_signatures)

    def _Create(self, part_a=True):
        """Create a given payload, if it doesn't already exist.

        Args:
            part_a: True to extract default/A partition.

        Raises:
            PayloadGenerationSkippedException: If paygen was skipped for any
            reason.
        """

        logging.info(
            "Generating %s payload %s",
            "delta" if self.payload.src_image else "full",
            self.payload,
        )

        # TODO(lamontjones): Trial test of wrapping the downloads in the
        #   semaphore in addition to the actual generation of the unsigned
        #   payload.  See if the running of several gsutil cp commands in
        #   parallel is increasing the likelihood of EAGAIN from spawning a
        #   thread.  See crbug.com/1016555.
        #
        # Run delta_generator for the purpose of generating an unsigned payload
        # with considerations for available memory. This is an adaption of the
        # previous version which used a simple semaphore. This was highly
        # limiting because while delta_generator is parallel there are single
        # threaded portions of it that were taking a very long time (i.e. long
        # poles).
        #
        # Sometimes if a process cannot acquire the lock for a long period of
        # time, the builder kills the process for not outputting any logs. So
        # here we try to acquire the lock with a timeout of ten minutes in a
        # loop and log some output so not to be killed by the builder.
        while True:
            acq_result = _mem_semaphore.acquire(timeout=self._SEMAPHORE_TIMEOUT)
            if acq_result.result:
                logging.info("Acquired lock (reason: %s)", acq_result.reason)
                break
            else:
                logging.info(
                    "Still waiting to run this particular payload (reason: %s)"
                    ", trying again ...",
                    acq_result.reason,
                )

        # Time the actual paygen operation started.
        start_time = datetime.datetime.now()

        try:
            # Fetch and prepare the tgt image.
            self._PrepareImage(self.payload.tgt_image, self.tgt_image_file)

            # Fetch and prepare the src image.
            if self.payload.src_image:
                self._PrepareImage(self.payload.src_image, self.src_image_file)

            # Check if payload generation should proceed.
            self._MaybeSkipPayloadGeneration()

            # Setup parameters about the payload like whether it is a DLC or
            # not. Or parameters like the APPID, etc.
            self._PreparePartitions(part_a)

            # Generate the unsigned payload.
            self._GenerateUnsignedPayload()
        except PayloadGenerationSkippedException:
            logging.info("Skipping payload generation.")
            raise
        finally:
            _mem_semaphore.release()
            # Time the actual paygen operation ended.
            end_time = datetime.datetime.now()
            logging.info(
                "* Finished payload generation in %s", end_time - start_time
            )

        # Sign the payload, if needed.
        _, metadata_signatures = self._SignPayload()

        # Store hash and signatures json.
        self._StorePayloadJson(metadata_signatures)

    def _VerifyPayload(self):
        """Checks the integrity of the generated payload.

        Raises:
            PayloadVerificationError when the payload fails to verify.
        """
        if self.signer:
            payload_file_name = self.signed_payload_file
            metadata_sig_file_name = self.metadata_signature_file
        else:
            payload_file_name = self.payload_file
            metadata_sig_file_name = None

        is_delta = bool(self.payload.src_image)

        logging.info(
            "Applying %s payload and verifying result",
            "delta" if is_delta else "full",
        )

        # This command checks both the payload integrity and applies the payload
        # to source and target partitions.
        cmd = [
            "check_update_payload",
            self.chroot.chroot_path(payload_file_name),
            "--check",
            "--type",
            "delta" if is_delta else "full",
            "--disabled_tests",
            "move-same-src-dst-block",
            "--part_names",
        ]
        cmd.extend(self.partition_names)
        cmd += ["--dst_part_paths"]
        cmd.extend(self.chroot.chroot_path(x) for x in self.tgt_partitions)
        if metadata_sig_file_name:
            cmd += [
                "--meta-sig",
                self.chroot.chroot_path(metadata_sig_file_name),
            ]

        cmd += ["--metadata-size", str(self.metadata_size)]

        if is_delta:
            cmd += ["--src_part_paths"]
            cmd.extend(self.chroot.chroot_path(x) for x in self.src_partitions)

        # We signed it with the private key, now verify it with the public key.
        if self.signer and self.signer.public_key:
            cmd += ["--key", self.chroot.chroot_path(self.signer.public_key)]

        self._RunGeneratorCmd(cmd)

    def _UploadResults(self):
        """Copy the payload generation results to the specified destination.

        Returns:
            A string uri to uploaded payload.
        """

        if self.payload.uri is None:
            logging.info("Not uploading payload.")
            return

        uri = self.payload.uri
        if self.rand:
            split = self.payload.uri.rstrip("/").rpartition("/")
            split = split[:-1] + (
                f"{split[-1]}-{cros_build_lib.GetRandomString()}",
            )
            uri = "".join(split)
        logging.info("Uploading payload to %s.", uri)

        # Deliver the payload to the final location.
        if self.signer:
            urilib.Copy(self.signed_payload_file, uri)
        else:
            urilib.Copy(self.payload_file, uri)

        # Upload payload related artifacts.
        urilib.Copy(self.log_file, self._LogsUri(uri))
        urilib.Copy(self.description_file, self._JsonUri(uri))

        return uri

    def _Run(self, part_a: bool = True):
        """Run* method helper to create, verify, and upload results.

        Args:
            part_a: True to extract default/A partition.

        Returns:
            A tuple of local payload path and remote URI. If not uploaded, the
            remote URI will be None.

        Raises:
            PayloadGenerationSkippedException: If paygen was skipped for any
            reason.
        """
        self._SetupNewFileNames()
        try:
            self._Create(part_a=part_a)
            if self._verify:
                self._VerifyPayload()
            if self._upload:
                ret_uri = self._UploadResults()
        except PayloadGenerationSkippedException as ex:
            if self._verify:
                print("Not verifying payload, because paygen was skipped.")
            if self._upload:
                print("Not uploading payload, because paygen was skipped.")
            raise ex

        return (self.payload_file, ret_uri)

    def Run(self):
        """Create, verify, and upload the results.

        Returns:
            A dict() of recovery key to tuple of payload local path and remote
            URI. Remote URI will be None if it wasn't uploaded.

            The keys will always be a positive integer starting from 1.

            e.g.
            {
                1: ("<local_path>", "<remote_path>"),
                2: ("<local_path>", "<remote_path>"),
                ...
            }

        Raises:
            PayloadGenerationSkippedException: If paygen was skipped for any
            reason.
        """
        logging.info("* Starting payload generation")
        start_time = datetime.datetime.now()

        if not self.payload.minios:
            ret = {
                1: self._Run(),
            }
        else:
            ret = {
                1: self._Run(part_a=True),
                2: self._Run(part_a=False),
            }
        logging.info(
            "Generated payload(s): %s", pformat.json(ret, compact=False)
        )

        end_time = datetime.datetime.now()
        logging.info(
            "* Total elapsed payload generation in %s", end_time - start_time
        )
        return ret


def GenerateUpdatePayload(
    chroot: chroot_lib.Chroot,
    tgt_image: str,
    payload: str,
    src_image: Optional[str] = None,
    work_dir: Optional[Union[str, os.PathLike]] = None,
    private_key: Optional[str] = None,
    check: bool = False,
    minios: bool = False,
    version=None,
) -> List[str]:
    """Generates output payload and verifies its integrity if needed.

    Args:
        chroot: Chroot to operate with.
        tgt_image: The path (or uri) to the image.
        payload: The path (or uri) to the output payload
        src_image: The path (or uri) to the source image. If passed, a delta
            payload is generated.
        work_dir: A working directory inside the chroot. The None, caller has
            the responsibility to clean up this directory after this function
            returns.
        private_key: The private key to sign the payload.
        check: If True, it will check the integrity of the generated payload.
        minios: If True, extract the minios partition instead of root and
            kernel.

    Returns:
        Returns a list of payload remote result paths, or an empty list if none
        were generated.
    """
    if path_util.DetermineCheckout().type != path_util.CheckoutType.REPO:
        raise Error("Need a chromeos checkout to generate payloads.")

    tgt_image = gspaths.Image(uri=tgt_image, image_version=version)
    src_image = gspaths.Image(uri=src_image) if src_image else None

    payload = gspaths.Payload(
        tgt_image=tgt_image, src_image=src_image, uri=payload, minios=minios
    )
    with chroot.tempdir() as temp_dir:
        work_dir = work_dir if work_dir is not None else temp_dir
        signer = None
        # Sign if a private key is passed in.
        if private_key is not None:
            signer = PaygenSigner(
                chroot=chroot, work_dir=work_dir, private_key=private_key
            )
        paygen = PaygenPayload(
            chroot, payload, work_dir, signer=signer, verify=check
        )
        try:
            results = paygen.Run()
            remote_paths = [paths[1] for paths in results.values()]
        except PayloadGenerationSkippedException:
            logging.info("No payload generated.")
            return []

    return remote_paths


def GenerateUpdatePayloadPropertiesFile(payload, output=None):
    """Generates the update payload's properties file.

    Args:
        payload: The path to the input payload.
        output: The path to the output properties json file. If None, the file
            will be placed by appending '.json' to the payload file itself.
    """
    if not output:
        output = payload + ".json"

    chroot = chroot_lib.Chroot()
    with chroot.tempdir() as work_dir:
        paygen = PaygenPayload(chroot, None, work_dir)
        properties_map = paygen.GetPayloadPropertiesMap(payload)
        pformat.json(properties_map, fp=output, compact=True)
