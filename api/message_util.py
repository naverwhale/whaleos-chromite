# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Protobuf message utilities.

The Serializer classes are adapters to standardize the reading and writing of
different protobuf message serialization formats to and from a message.

The base MessageHandler class encapsulates the functionality of reading
a file containing serialized data into a protobuf message instance, and
writing serialized data from a message instance out to a file.
"""

import json
import logging
import os
from typing import Optional, TYPE_CHECKING

from chromite.third_party.google.protobuf import json_format

from chromite.lib import osutils
from chromite.utils import pformat


if TYPE_CHECKING:
    from chromite.third_party import google

FORMAT_BINARY = 1
FORMAT_JSON = 2
VALID_FORMATS = (FORMAT_BINARY, FORMAT_JSON)


class Error(Exception):
    """Base error class for the module."""


class InvalidInputFileError(Error):
    """Raised when the input file cannot be read."""


class InvalidInputFormatError(Error):
    """Raised when the passed input protobuf can't be parsed."""


class InvalidOutputFileError(Error):
    """Raised when the output file cannot be written."""


class UnknownHandlerError(Error):
    """Raised when a valid type has not been implemented yet.

    This should only ever be raised when under active development.
    See: get_message_handler.
    """


def get_message_handler(path, msg_format):
    """Get a message handler to handle the given message format."""
    assert msg_format in VALID_FORMATS

    if msg_format == FORMAT_BINARY:
        return MessageHandler(
            path=path,
            serializer=BinarySerializer(),
            binary=True,
            input_arg="--input-binary",
            output_arg="--output-binary",
            config_arg="--config-binary",
        )
    elif msg_format == FORMAT_JSON:
        return MessageHandler(
            path=path,
            serializer=JsonSerializer(),
            binary=False,
            input_arg="--input-json",
            output_arg="--output-json",
            config_arg="--config-json",
        )
    else:
        # Unexpected. Your new format type needs a case in this function if
        # you got this error.
        raise UnknownHandlerError("Unknown format type.")


class Serializer:
    """Base (and null) serializer class."""

    def deserialize(self, data: str, message: "google.protobuf.Message"):
        """Deserialize the data into the given message.

        Args:
            data: The message data to deserialize.
            message: The message to load the data into.
        """

    # pylint: disable=unused-argument
    def serialize(self, message: "google.protobuf.Message") -> str:
        """Serialize the message data.

        Args:
            message: The message to be serialized.

        Returns:
            The message's serialized data.
        """
        return ""


class BinarySerializer(Serializer):
    """Protobuf binary serializer class."""

    def deserialize(self, data, message):
        """Deserialize the data into the given message.

        See: Serializer.deserialize
        """
        message.ParseFromString(data)

    def serialize(self, message):
        """Serialize the message data.

        See: Serializer.serialize
        """
        return message.SerializeToString()


class JsonSerializer(Serializer):
    """Protobuf json serializer class."""

    def deserialize(self, data, message):
        """Deserialize the data into the given message.

        See: Serializer.deserialize
        """
        try:
            json_format.Parse(data, message, ignore_unknown_fields=True)
        except json_format.ParseError as e:
            raise InvalidInputFormatError(
                "Unable to parse the input json: %s" % e
            )

    def serialize(self, message):
        """Serialize the message data.

        See: Serializer.serialize
        """
        result = json_format.MessageToJson(
            message, sort_keys=True, use_integers_for_enums=True
        )
        if not result:
            return "{}"

        return pformat.json(json.loads(result), compact=True)


class MessageHandler:
    """Class to handle message (de)serialization to and from files.

    The class is fairly tightly coupled to the build api, but we currently have
    no other projected use cases for this, so it's handy. In particular, if we
    scrap the "maintain the same input/output/config serialization when
    reexecing inside the chroot" convention, this implementation is much less
    useful and can be fairly trivially generalized.

    The instance's path is the primary path the message handler was built for.
    For the Build API, this means one of the input/output/config arguments. In
    practice, it's largely a convenience/shortcut so we don't have to either
    track which input files are what types (which we know from the argument used
    to pass them in), or create another containing data class for the
    functionality provided by the handler and serializer classes and the build
    api data.

    Examples:
        message_handler = MessageHandler(path, ...)
        message = ...
        # Parse path into message.
        message_handler.read_into(message)
        # Write message to a different file.
        message_handler.write_into(message, path=other_path)
    """

    def __init__(
        self,
        path: str,
        serializer: Serializer,
        binary: bool,
        input_arg: str,
        output_arg: str,
        config_arg: str,
    ):
        """MessageHandler init.

        Args:
            path: The path to the main file associated with this handler.
            serializer: The serializer to be used for the messages.
            binary: Whether the serialized content is binary.
            input_arg: The --input-x argument used for this type. Used for
                reexecution inside the chroot.
            output_arg: The --output-x argument used for this type. Used for
                reexecution inside the chroot.
            config_arg: The --config-x argument used for this type. Used for
                reexecution inside the chroot.
        """
        self.path = path
        self.serializer = serializer
        self.read_mode = "rb" if binary else "r"
        self.write_mode = "wb" if binary else "w"
        self.input_arg = input_arg
        self.output_arg = output_arg
        self.config_arg = config_arg

    def read_into(
        self, message: "google.protobuf.Message", path: Optional[str] = None
    ):
        """Read a file containing serialized data into a message.

        Args:
            message: The message to populate.
            path: A path to read. Uses the instance's path when not given.

        Raises:
            InvalidInputFileError: When a path has not been given, does not
                exist, or cannot be read.
        """
        target_path = path or self.path
        if not target_path:
            raise InvalidInputFileError("No input file has been specified.")
        if not os.path.exists(target_path):
            raise InvalidInputFileError("The input file does not exist.")

        try:
            content = osutils.ReadFile(target_path, mode=self.read_mode)
        except IOError as e:
            raise InvalidInputFileError("Unable to read input file: %s" % e)

        if content:
            self.serializer.deserialize(content, message)
        else:
            logging.warning(
                "No content found in %s to deserialize.", target_path
            )

    def write_from(
        self, message: "google.protobuf.Message", path: Optional[str] = None
    ):
        """Write serialized data from the message to a file.

        Args:
            message: The message to serialize and persist.
            path: An optional override of the instance's path.

        Raises:
            InvalidOutputFileError: When no path given, or the path cannot be
                written to.
        """
        if not path and not self.path:
            raise InvalidOutputFileError("No output file has been specified.")

        try:
            osutils.WriteFile(
                path or self.path,
                self.serializer.serialize(message),
                mode=self.write_mode,
            )
        except IOError as e:
            raise InvalidOutputFileError("Cannot write output file: %s" % e)
