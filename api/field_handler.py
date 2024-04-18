# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Field handler classes.

The field handlers are meant to parse information from or do some other generic
action for a specific field type for the build_api script.
"""

import contextlib
import functools
import logging
import os
import shutil
from typing import Iterator, List, Optional

from chromite.third_party.google.protobuf import message as protobuf_message

from chromite.api.controller import controller_util
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import chroot_lib
from chromite.lib import osutils


class Error(Exception):
    """Base error class for the module."""


class InvalidResultPathError(Error):
    """Result path is invalid."""


class MissingChrootMessage(Error):
    """Message is missing Chroot field."""


class InvalidPathHandlerError(Error):
    """PathHandler params are invalid."""


class ChrootHandler:
    """Translate a Chroot message to chroot enter arguments and env."""

    def __init__(self, clear_field):
        self.clear_field = clear_field

    def handle(self, message, recurse=True) -> Optional["chroot_lib.Chroot"]:
        """Parse a message for a chroot field."""
        # Find the Chroot field. Search for the field by type to prevent it
        # being tied to a naming convention.
        for descriptor in message.DESCRIPTOR.fields:
            field = getattr(message, descriptor.name)
            if isinstance(field, common_pb2.Chroot):
                chroot = field
                if self.clear_field:
                    message.ClearField(descriptor.name)
                return self.parse_chroot(chroot)

        # Recurse down one level. This is handy for meta-endpoints that use
        # another endpoint's request to produce data for or about the second
        # endpoint. e.g. PackageService/NeedsChromeSource.
        if recurse:
            for descriptor in message.DESCRIPTOR.fields:
                field = getattr(message, descriptor.name)
                if isinstance(field, protobuf_message.Message):
                    chroot = self.handle(field, recurse=False)
                    if chroot:
                        return chroot

        # Complain loudly if a message is used without a Chroot field.
        raise MissingChrootMessage("No chroot message found.")

    def parse_chroot(
        self, chroot_message: common_pb2.Chroot
    ) -> "chroot_lib.Chroot":
        """Parse a Chroot message instance."""
        return controller_util.ParseChroot(chroot_message)


def handle_chroot(
    message: protobuf_message.Message, clear_field: bool = True
) -> "chroot_lib.Chroot":
    """Find and parse the chroot field, returning the Chroot instance."""
    handler = ChrootHandler(clear_field)
    return handler.handle(message)


def handle_goma(message, chroot_path, out_path):
    """Find and parse the GomaConfig field, returning the Goma instance."""
    for descriptor in message.DESCRIPTOR.fields:
        field = getattr(message, descriptor.name)
        if isinstance(field, common_pb2.GomaConfig):
            goma_config = field
            return controller_util.ParseGomaConfig(
                goma_config, chroot_path, out_path
            )

    return None


def handle_remoteexec(message: protobuf_message.Message):
    """Find the RemoteexecConfig field, returning the Remoteexec instance."""
    for descriptor in message.DESCRIPTOR.fields:
        field = getattr(message, descriptor.name)
        if isinstance(field, common_pb2.RemoteexecConfig):
            remoteexec_config = field
            return controller_util.ParseRemoteexecConfig(remoteexec_config)

    return None


class PathHandler:
    """Handles transferring a file or directory into or out of the chroot."""

    INSIDE = common_pb2.Path.INSIDE
    OUTSIDE = common_pb2.Path.OUTSIDE

    def __init__(
        self,
        field: common_pb2.Path,
        destination: str,
        delete: bool,
        chroot: Optional[chroot_lib.Chroot] = None,
        reset: Optional[bool] = True,
    ) -> None:
        """Path handler initialization.

        Args:
            field: The Path message.
            destination: The destination base path. If not set, paths are
                translated only.
            delete: Whether the copied file(s) should be deleted on cleanup.
            chroot: Chroot object to use for translating the paths in/out of
                the chroot as necessary -- modifying the destination path when
                moving files into the chroot, or modifying the source path when
                moving files outside.
            reset: Whether to reset the state on cleanup.
        """
        assert isinstance(field, common_pb2.Path)
        assert field.path
        assert field.location
        if delete and not destination:
            raise InvalidPathHandlerError(
                "`delete` cannot be set with no destination."
            )

        self.field = field
        self.destination = destination
        self.chroot = chroot
        self.delete = delete
        self.tempdir = None
        self.reset = reset

        # For resetting the state.
        self._transferred = False
        self._original_message = common_pb2.Path()
        self._original_message.CopyFrom(self.field)

    def transfer(self, direction: int) -> None:
        """Copy the file or directory to its destination.

        Args:
            direction: The direction files are being copied (into or out of the
            chroot). Specifying the direction allows avoiding performing
            unnecessary copies.
        """
        if self._transferred:
            return

        assert direction in [self.INSIDE, self.OUTSIDE]

        if self.field.location == direction:
            # Already in the correct location, nothing to do.
            return

        # Create a tempdir for the copied file if we're cleaning it up
        # afterwards.
        if self.delete:
            self.tempdir = osutils.TempDir(base_dir=self.destination)
            destination = self.tempdir.tempdir
        else:
            destination = self.destination

        source = self.field.path
        if direction == self.OUTSIDE and self.chroot:
            source = self.chroot.full_path(source)

        if not destination:
            # Handle TRANSFER_TRANSLATE. Either `Chroot.full_path` or
            # `Chroot.chroot_path` will do the actual translation.
            dest_path = source
        else:
            if os.path.isfile(source):
                # File - use old file name, just copy it into the destination.
                dest_path = os.path.join(destination, os.path.basename(source))
                copy_fn = shutil.copy
            else:
                # Directory - just copy everything into the new location.
                dest_path = destination
                copy_fn = functools.partial(
                    osutils.CopyDirContents, allow_nonempty=True
                )

            logging.debug("Copying %s to %s", source, dest_path)
            copy_fn(source, dest_path)

        # Clean up the destination path for returning, if applicable.
        return_path = dest_path
        if direction == self.INSIDE and self.chroot:
            return_path = self.chroot.chroot_path(return_path)

        if not destination:
            logging.debug("Translated %s to %s", self.field.path, return_path)

        self.field.path = return_path
        self.field.location = direction
        self._transferred = True

    def cleanup(self):
        """Post-execution cleanup."""
        if self.tempdir:
            self.tempdir.Cleanup()
            self.tempdir = None

        if self.reset:
            self.field.CopyFrom(self._original_message)


class SyncedDirHandler:
    """Handler for syncing directories across the chroot boundary."""

    def __init__(
        self,
        field: common_pb2.SyncedDir,
        destination: str,
        chroot: chroot_lib.Chroot,
    ):
        self.field = field
        self.chroot = chroot

        self.source = self.field.dir
        if not self.source.endswith(os.sep):
            self.source += os.sep

        self.destination = destination
        if not self.destination.endswith(os.sep):
            self.destination += os.sep

        # For resetting the message later.
        self._original_message = common_pb2.SyncedDir()
        self._original_message.CopyFrom(self.field)

    def _sync(self, src, dest):
        logging.info("Syncing %s to %s", src, dest)
        # TODO: This would probably be more efficient with rsync.
        osutils.EmptyDir(dest)
        osutils.CopyDirContents(src, dest)

    def sync_in(self):
        """Sync files from the source directory to the destination directory."""
        self._sync(self.source, self.destination)
        self.field.dir = self.chroot.chroot_path(self.destination)

    def sync_out(self):
        """Sync files from the destination directory to the source directory."""
        self._sync(self.destination, self.source)
        self.field.CopyFrom(self._original_message)


@contextlib.contextmanager
def copy_paths_in(
    message: protobuf_message.Message,
    destination: str,
    delete: Optional[bool] = True,
    chroot: Optional[chroot_lib.Chroot] = None,
) -> Iterator[List[PathHandler]]:
    """Context manager function to transfer and cleanup all Path messages.

    Args:
        message: A message whose Path messages should be transferred.
        destination: The base destination path.
        delete: Whether the file(s) should be deleted.
        chroot: Chroot object to use for translating the final destination path
            into the chroot.

    Yields:
        list[PathHandler]: The path handlers.
    """
    assert destination

    handlers = _extract_handlers(
        message, destination, chroot, delete=delete, reset=True
    )

    for handler in handlers:
        handler.transfer(PathHandler.INSIDE)

    try:
        yield handlers
    finally:
        for handler in handlers:
            handler.cleanup()


@contextlib.contextmanager
def sync_dirs(
    message: protobuf_message.Message,
    destination: str,
    chroot: chroot_lib.Chroot,
) -> Iterator[SyncedDirHandler]:
    """Context manager function to handle SyncedDir messages.

    The sync semantics are effectively:
        rsync -r --del source/ destination/
        * The endpoint runs. *
        rsync -r --del destination/ source/

    Args:
        message: A message whose SyncedPath messages should be synced.
        destination: The destination path.
        chroot: Chroot object to use for translating the final destination path
            into the chroot.

    Yields:
        The handlers.
    """
    assert destination

    handlers = _extract_handlers(
        message,
        destination,
        chroot=chroot,
        delete=False,
        reset=True,
        message_type=common_pb2.SyncedDir,
    )

    for handler in handlers:
        handler.sync_in()

    try:
        yield handlers
    finally:
        for handler in handlers:
            handler.sync_out()


def extract_results(
    request_message: protobuf_message.Message,
    response_message: protobuf_message.Message,
    chroot: "chroot_lib.Chroot",
) -> None:
    """Transfer all response Path messages to the request's ResultPath.

    Args:
        request_message: The request message containing a ResultPath message.
        response_message: The response message whose Path message(s) are to be
            transferred.
        chroot: The chroot the files are being copied out of.
    """
    # Find the ResultPath.
    for descriptor in request_message.DESCRIPTOR.fields:
        field = getattr(request_message, descriptor.name)
        if isinstance(field, common_pb2.ResultPath):
            result_path_message = field
            break
    else:
        # No ResultPath to handle.
        return

    destination = result_path_message.path.path
    if result_path_message.transfer == common_pb2.ResultPath.TRANSFER_TRANSLATE:
        if destination:
            raise InvalidResultPathError(
                "ResultPath.path must be empty for TRANSFER_TRANSLATE."
                f" Value=`{destination}`."
            )
    elif not destination:
        # ResultPath wasn't filled; don't copy to undefined location.
        return

    handlers = _extract_handlers(
        response_message, destination, chroot=chroot, delete=False, reset=False
    )

    for handler in handlers:
        handler.transfer(PathHandler.OUTSIDE)
        handler.cleanup()


def _extract_handlers(
    message,
    destination,
    chroot,
    delete=False,
    reset=False,
    field_name=None,
    message_type=None,
):
    """Recursive helper for handle_paths to extract Path messages."""
    message_type = message_type or common_pb2.Path
    is_path_target = message_type is common_pb2.Path
    is_synced_target = message_type is common_pb2.SyncedDir

    is_message = isinstance(message, protobuf_message.Message)
    is_result_path = isinstance(message, common_pb2.ResultPath)
    if not is_message or is_result_path:
        # Base case: Nothing to handle.
        # There's nothing we can do with scalar values.
        # Skip ResultPath instances to avoid unnecessary file copying.
        return []
    elif is_path_target and isinstance(message, common_pb2.Path):
        # Base case: Create handler for this message.
        if not message.path or not message.location:
            logging.debug("Skipping %s; incomplete.", field_name or "message")
            return []

        handler = PathHandler(
            message, destination, delete=delete, chroot=chroot, reset=reset
        )
        return [handler]
    elif is_synced_target and isinstance(message, common_pb2.SyncedDir):
        if not message.dir or not destination:
            logging.debug(
                "Skipping %s; no directory given or missing destination.",
                field_name or "message",
            )
            return []

        handler = SyncedDirHandler(message, destination, chroot)
        return [handler]

    # Iterate through each field and recurse.
    handlers = []
    for descriptor in message.DESCRIPTOR.fields:
        field = getattr(message, descriptor.name)
        if field_name:
            new_field_name = "%s.%s" % (field_name, descriptor.name)
        else:
            new_field_name = descriptor.name

        if isinstance(field, protobuf_message.Message):
            # Recurse for nested Paths.
            handlers.extend(
                _extract_handlers(
                    field,
                    destination,
                    chroot,
                    delete,
                    reset,
                    field_name=new_field_name,
                    message_type=message_type,
                )
            )
        else:
            # If it's iterable it may be a repeated field, try each element.
            try:
                iterator = iter(field)
            except TypeError:
                # Definitely not a repeated field, just move on.
                continue

            for element in iterator:
                handlers.extend(
                    _extract_handlers(
                        element,
                        destination,
                        chroot,
                        delete,
                        reset,
                        field_name=new_field_name,
                        message_type=message_type,
                    )
                )

    return handlers
