# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Parse and modify disk layout information."""

import copy
import json
import logging
import math
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union

from chromite.lib import constants
from chromite.lib import json_lib


class Error(Exception):
    """Raised when there is an error with Cgpt."""


class ConfigNotFoundError(Error):
    """Config Not Found"""


class PartitionNotFoundError(Error):
    """Partition Not Found"""


class InvalidLayoutError(Error):
    """Invalid Layout"""


class InvalidAdjustmentError(Error):
    """Invalid Adjustment"""


class InvalidSizeError(Error):
    """Invalid Size"""


class ConflictingPartitionOrderError(Error):
    """The partition order in the parent and child layout don't match."""


class MismatchedRootfsFormatError(Error):
    """Rootfs partitions in different formats"""


class MismatchedRootfsBlocksError(Error):
    """Rootfs partitions have different numbers of reserved erase blocks"""


class MissingEraseBlockFieldError(Error):
    """Partition has reserved erase blocks but not other fields needed"""


class ExcessFailureProbabilityError(Error):
    """Chances are high that the partition will have too many bad blocks"""


class UnalignedPartitionError(Error):
    """Partition size does not divide erase block size"""


class ExpandNandImpossibleError(Error):
    """Partition is raw NAND and marked with the incompatible expand feature"""


class ExcessPartitionSizeError(Error):
    """Partitions sum to more than the size of the whole device"""


COMMON_LAYOUT = "common"
BASE_LAYOUT = "base"
# Blocks of the partition entry array.
SIZE_OF_PARTITION_ENTRY_ARRAY_BYTES = 16 * 1024
SIZE_OF_PMBR = 1
SIZE_OF_GPT_HEADER = 1
DEFAULT_SECTOR_SIZE = 512
MAX_SECTOR_SIZE = 8 * 1024
START_SECTOR = 4 * MAX_SECTOR_SIZE
SECONDARY_GPT_BYTES = (
    SIZE_OF_PARTITION_ENTRY_ARRAY_BYTES + SIZE_OF_GPT_HEADER * MAX_SECTOR_SIZE
)


def ParseHumanNumber(operand: Union[str, int]) -> int:
    """Parse a human friendly number

    This parses things like 4GiB and 4MB and converts them to size in Bytes.

    Args:
        operand: The number to parse.

    Returns:
        The parsed size in Bytes.

    Raises:
        InvalidAdjustmentError when the input argument is invalid.
    """
    operand = str(operand)
    negative = -1 if operand.startswith("-") else 1
    if negative == -1:
        operand = operand[1:]
    operand_digits = re.sub(r"\D", r"", operand)
    if not operand_digits:
        raise InvalidAdjustmentError(
            "Numeric value could not be parsed from: %s" % operand
        )

    size_factor = block_factor = 1
    suffix = operand[len(operand_digits) :].strip()
    if suffix:
        size_factors = {
            "B": 0,
            "K": 1,
            "M": 2,
            "G": 3,
            "T": 4,
        }
        try:
            size_factor = size_factors[suffix[0].upper()]
        except KeyError:
            raise InvalidAdjustmentError("Unknown size type %s" % suffix)
        if size_factor == 0 and len(suffix) > 1:
            raise InvalidAdjustmentError("Unknown size type %s" % suffix)
        block_factors = {
            "": 1024,
            "B": 1000,
            "IB": 1024,
        }
        try:
            block_factor = block_factors[suffix[1:].upper()]
        except KeyError:
            raise InvalidAdjustmentError("Unknown size type %s" % suffix)

    return int(operand_digits) * pow(block_factor, size_factor) * negative


def ProduceHumanNumber(number: int) -> str:
    """Converts size in bytes to human readable format, like GiB, MB.

    Args:
        number: A number to be converted to human form.

    Returns:
        Human readable memory size value, such as "1 KiB", that satisfies the
        condition ParseHumanNumber(ProduceHumanNumber(i)) == i.
    """
    scales = [
        (2**40, "Ti"),
        (10**12, "T"),
        (2**30, "Gi"),
        (10**9, "G"),
        (2**20, "Mi"),
        (10**6, "M"),
        (2**10, "Ki"),
        (10**3, "K"),
    ]
    for denom, suffix in scales:
        if (number % denom) == 0:
            return "%d %sB" % (number // denom, suffix)
    return str(number)


def ParseRelativeNumber(
    max_number: Union[int, str], number: Union[int, str]
) -> int:
    """Return the number that is relative to |max_number| by |number|

    We support three forms:
     90% - |number| is a percentage of |max_number|
     100 - |number| is the answer already (and |max_number| is ignored)
     -90 - |number| is subtracted from |max_number|

    Args:
        max_number: The limit to use when |number| is negative or a percent
        number: The (possibly relative) number to parse
            (may be an int or string)

    Returns:
        Returns a relative number.
    """
    max_number = int(max_number)
    number = str(number)

    if number.endswith("%"):
        percent = int(number[:-1]) / 100
        return int(max_number * percent)

    number = ParseHumanNumber(number)
    if number < 0:
        return max_number + number
    else:
        return number


def GetScriptShell() -> str:
    """Loads and returns the skeleton script for our output script.

    Returns:
        A string containing the skeleton script
    """

    script_shell_path = constants.CHROMITE_DIR / "sdk" / "cgpt_shell.sh"
    with open(script_shell_path, "r", encoding="utf-8") as f:
        script_shell = "".join(f.readlines())

    # Before we return, insert the path to this tool so somebody reading the
    # script later can tell where it was generated.
    script_shell = script_shell.replace(
        "@SCRIPT_GENERATOR@", str(script_shell_path)
    )

    return script_shell


def Combinations(n: int, k: int) -> int:
    """Calculate the binomial coefficient, i.e., "n choose k"

    This calculates the number of ways that k items can be chosen from
    a set of size n. For example, if there are n blocks and k of them
    are bad, then this returns the number of ways that the bad blocks
    can be distributed over the device.
    See http://en.wikipedia.org/wiki/Binomial_coefficient

    For convenience to the caller, this function allows impossible cases
    as input and returns 0 for them.
    """
    if k < 0 or n < k:
        return 0
    return math.factorial(n) // (math.factorial(k) * math.factorial(n - k))


class DiskLayout:
    """Class that is used to parse, get and modify disk_layout.json file."""

    def __init__(
        self,
        disk_layout_path: Optional[Union[os.PathLike, str]] = None,
        adjust_partition: Optional[List[str]] = None,
    ):
        """Init Method.

        Specify the disk layout path and the partition adjustments that need to
        be applied.

        The adjust partition should be of the format,
            <label>:<op><size>
        Where:
            <label> is a label name as found in the disk layout file
            <op> is one of the three: + - =
            <size> is a number followed by an optional size qualifier:
                B, KiB, MiB, GiB, TiB: bytes, kibi-, mebi-, gibi-, tebi-
                    (base 1024)
                B,   K,   M,   G,   T: short hand for above
                B,  KB,  MB,  GB,  TB: bytes, kilo-, mega-, giga-, tera-
                    (base 1000)

        This will set the ROOT-A partition size to 1 gibibytes
        (1024 * 1024 * 1024 * 1):
            --adjust_part ROOT-A:=1GiB
        This will grow the ROOT-A partition size by 500 mebibytes
        (1024 * 1024 * 500):
            --adjust_part ROOT-A:+500MiB
        This will shrink the ROOT-A partition size by 10 mebibytes
        (1024 * 1024 * 10):
            --adjust_part ROOT-A:-20MiB

        Args:
            disk_layout_path: The disk layout file path.
            adjust_partition: Partition adjustment that needs to be applied.
        """
        self._disk_layout_path = disk_layout_path or self._getDiskLayoutPath()
        self._disk_layout_config = self._loadPartitionConfig()
        self._image_partitions = {}
        for image_type in self.GetImageTypes():
            self._image_partitions[image_type] = self._getPartitionTable(
                image_type, adjust_partition
            )

    def _ApplyLayoutOverrides(
        self, layout_to_override: Dict[Any, Any], layout: Dict[Any, Any]
    ):
        """Applies |layout| overrides on to |layout_to_override|.

        First add missing partition from layout to layout_to_override.
        Then, update partitions in layout_to_override with layout information.

        Args:
            layout_to_override: The layout config that needs to be updated.
            layout: The layout config having the override values.
        """
        # First check that all the partitions defined in both layouts are
        # defined in the same order in each layout. Otherwise, the order in
        # which they end up in the merged layout doesn't match what the user
        # sees in the child layout.
        common_nums = set.intersection(
            {part["num"] for part in layout_to_override if "num" in part},
            {part["num"] for part in layout if "num" in part},
        )
        layout_to_override_order = [
            part["num"]
            for part in layout_to_override
            if part.get("num") in common_nums
        ]
        layout_order = [
            part["num"] for part in layout if part.get("num") in common_nums
        ]
        if layout_order != layout_to_override_order:
            raise ConflictingPartitionOrderError(
                "Layouts share partitions %s but they are in different order: "
                "layout_to_override: %s, layout: %s"
                % (
                    sorted(common_nums),
                    [part.get("num") for part in layout_to_override],
                    [part.get("num") for part in layout],
                )
            )

        # Merge layouts with the partitions in the same order they are in both
        # layouts.
        part_index = 0
        for part_to_apply in layout:
            num = part_to_apply.get("num")

            if part_index == len(layout_to_override):
                # The part_to_apply is past the list of partitions to override,
                # this means that is a new partition added at the end.
                # Need of deepcopy, in case we change layout later.
                layout_to_override.append(copy.deepcopy(part_to_apply))
            elif (
                layout_to_override[part_index].get("num") is None
                and num is None
            ):
                # Allow modifying gaps after a partition.
                # TODO(deymo): Drop support for "gap" partitions and use
                # alignment instead.
                layout_to_override[part_index].update(part_to_apply)
            elif num in common_nums:
                while layout_to_override[part_index].get("num") != num:
                    part_index += 1
                layout_to_override[part_index].update(part_to_apply)
            else:
                # Need of deepcopy, in case we change layout later.
                layout_to_override.insert(
                    part_index, copy.deepcopy(part_to_apply)
                )
            part_index += 1

    def _LoadStackedPartitionConfig(
        self, filename: Union[str, os.PathLike]
    ) -> Dict[Any, Any]:
        """Loads a partition table and its possible parent tables.

        This does very little validation.  It's just enough to walk all of the
        parent files and merges them with the current config.  Overall
        validation is left to the caller.

        Args:
            filename: Filename to parse.

        Returns:
            Object containing disk layout configuration.

        Raises:
            ConfigNotFoundError, when the file doesnt exists.
        """
        filename = Path(filename)
        if not filename.exists():
            raise ConfigNotFoundError(
                "Partition config %s was not found!" % filename
            )
        config = json_lib.ParseJsonFileWithComments(filename)

        parents = config.get("parent", "").split()
        if isinstance(parents, list):
            parents.reverse()

        # When there are no parents, just apply the common layout into
        # the other ones.
        if not parents:
            common_layout = config.get("layouts", {}).setdefault(
                COMMON_LAYOUT, []
            )
            for layout_name, layout in config.get("layouts", {}).items():
                # Don't apply on yourself.
                if layout_name in (COMMON_LAYOUT, "_comment"):
                    continue

                # Need to copy a list of dicts so make a deep copy.
                working_layout = copy.deepcopy(common_layout)
                self._ApplyLayoutOverrides(working_layout, layout)
                config["layouts"][layout_name] = working_layout
            return config

        dirname = filename.parent
        # When there is parent, apply the current config on top of a parent,
        # and reuse that produced config for the next parent.
        for parent in parents:
            parent_filename = dirname / parent
            if not parent_filename.exists():
                # Try loading the parent file from the src/scripts/build_library
                # directory.
                parent_filename = (
                    constants.CROSUTILS_DIR / "build_library" / parent
                )
            parent_config = self._LoadStackedPartitionConfig(parent_filename)

            # First if the parent is missing any fields the new config has, fill
            # them in.
            for key in config.keys():
                if key == "parent":
                    continue
                elif key == "metadata":
                    # We handle this especially to allow for inner metadata
                    # fields to be added / modified.
                    parent_config.setdefault(key, {})
                    parent_config[key].update(config[key])
                else:
                    parent_config.setdefault(key, config[key])

            # The overrides work by taking the parent_config, apply the new
            # config layout info, and return the resulting config which is
            # stored in the parent config.

            # So there's an issue where an inheriting layout file may contain
            # new layouts not previously defined in the parent layout. Since we
            # are building these layout files based on the parent configs and
            # overriding new values, we first add the new layouts not previously
            # defined in th parent config using a copy of the base layout from
            # that parent config.
            parent_layouts = set(parent_config.get("layouts", {}))
            config_layouts = set(config.get("layouts", {}))
            new_layouts = config_layouts - parent_layouts

            # Actually add the copy. Use a copy such that each is unique.
            parent_common_layout = parent_config.get("layouts", {}).setdefault(
                COMMON_LAYOUT, []
            )
            for layout_name in new_layouts:
                parent_config["layouts"][layout_name] = copy.deepcopy(
                    parent_common_layout
                )

            # Iterate through each layout in the parent config and apply the
            # new layout.
            common_layout = config.get("layouts", {}).setdefault(
                COMMON_LAYOUT, []
            )
            for layout_name, parent_layout in parent_config.get(
                "layouts", {}
            ).items():
                if layout_name == "_comment":
                    continue

                layout_override = config.get("layouts", {}).setdefault(
                    layout_name, []
                )
                if layout_name != COMMON_LAYOUT:
                    self._ApplyLayoutOverrides(parent_layout, common_layout)

                self._ApplyLayoutOverrides(parent_layout, layout_override)

            config = parent_config

        config.pop("parent", None)
        return config

    def _loadPartitionConfig(self) -> Dict[Any, Any]:
        """Loads a partition tables configuration file into a Python object.

        Args:
            filename: Filename to load into object

        Returns:
            Object containing disk layout configuration.

        Raises:
            ConfigNotFoundError, when the layout file doesnt exists.
            InvalidLayoutError when the partition configuration is invalid.
        """

        valid_keys = set(("_comment", "metadata", "layouts", "parent"))
        valid_layout_keys = set(
            (
                "_comment",
                "num",
                "fs_blocks",
                "fs_block_size",
                "fs_align",
                "bytes",
                "uuid",
                "label",
                "format",
                "fs_format",
                "type",
                "features",
                "size",
                "fs_size",
                "fs_options",
                "erase_block_size",
                "hybrid_mbr",
                "reserved_erase_blocks",
                "max_bad_erase_blocks",
                "external_gpt",
                "page_size",
                "size_min",
                "fs_size_min",
            )
        )
        valid_features = set(("expand", "last_partition"))

        config = self._LoadStackedPartitionConfig(self._disk_layout_path)
        try:
            metadata = config["metadata"]
            metadata["fs_block_size"] = ParseHumanNumber(
                metadata["fs_block_size"]
            )
            if metadata.get("fs_align") is None:
                metadata["fs_align"] = metadata["fs_block_size"]
            else:
                metadata["fs_align"] = ParseHumanNumber(metadata["fs_align"])

            if (metadata["fs_align"] < metadata["fs_block_size"]) or (
                metadata["fs_align"] % metadata["fs_block_size"]
            ):
                raise InvalidLayoutError(
                    "fs_align must be a multiple of fs_block_size"
                )

            unknown_keys = set(config.keys()) - valid_keys
            if unknown_keys:
                raise InvalidLayoutError("Unknown items: %r" % unknown_keys)

            if len(config["layouts"]) <= 0:
                raise InvalidLayoutError('Missing "layouts" entries')

            if not BASE_LAYOUT in config["layouts"].keys():
                raise InvalidLayoutError('Missing "base" config in "layouts"')

            for layout_name, layout in config["layouts"].items():
                if layout_name == "_comment":
                    continue

                for part in layout:
                    unknown_keys = set(part.keys()) - valid_layout_keys
                    if unknown_keys:
                        raise InvalidLayoutError(
                            "Unknown items in layout %s: %r"
                            % (layout_name, unknown_keys)
                        )

                    if part.get("num") == "metadata" and "type" not in part:
                        part["type"] = "blank"

                    if part["type"] != "blank":
                        for s in ("num", "label"):
                            if not s in part:
                                raise InvalidLayoutError(
                                    'Layout "%s" missing "%s"'
                                    % (layout_name, s)
                                )

                    if "size" in part:
                        part["bytes"] = ParseHumanNumber(part["size"])
                        if "size_min" in part:
                            size_min = ParseHumanNumber(part["size_min"])
                            if part["bytes"] < size_min:
                                part["bytes"] = size_min
                    elif part.get("num") != "metadata":
                        part["bytes"] = 1

                    if "fs_size" in part:
                        part["fs_bytes"] = ParseHumanNumber(part["fs_size"])
                        if "fs_size_min" in part:
                            fs_size_min = ParseHumanNumber(part["fs_size_min"])
                            if part["fs_bytes"] < fs_size_min:
                                part["fs_bytes"] = fs_size_min
                        if part["fs_bytes"] <= 0:
                            raise InvalidSizeError(
                                'File system size "%s" must be positive'
                                % part["fs_size"]
                            )
                        if part["fs_bytes"] > part["bytes"]:
                            raise InvalidSizeError(
                                "Filesystem may not be larger than partition: "
                                "%s %s: %d > %d"
                                % (
                                    layout_name,
                                    part["label"],
                                    part["fs_bytes"],
                                    part["bytes"],
                                )
                            )
                        if part["fs_bytes"] % metadata["fs_align"] != 0:
                            raise InvalidSizeError(
                                'File system size: "%s" (%s bytes) is not an '
                                "even multiple of fs_align: %s"
                                % (
                                    part["fs_size"],
                                    part["fs_bytes"],
                                    metadata["fs_align"],
                                )
                            )
                        if part.get("format") == "ubi":
                            part_meta = self._getMetadataPartition(layout)
                            page_size = ParseHumanNumber(part_meta["page_size"])
                            eb_size = ParseHumanNumber(
                                part_meta["erase_block_size"]
                            )
                            ubi_eb_size = eb_size - 2 * page_size
                            if (part["fs_bytes"] % ubi_eb_size) != 0:
                                # Trim fs_bytes to multiple of UBI eraseblock
                                # size.
                                fs_bytes = part["fs_bytes"] - (
                                    part["fs_bytes"] % ubi_eb_size
                                )
                                raise InvalidSizeError(
                                    'File system size: "%s" (%d bytes) is not '
                                    "a multiple of UBI erase block size (%d). "
                                    'Please set "fs_size" to "%s" in the '
                                    '"common" layout instead.'
                                    % (
                                        part["fs_size"],
                                        part["fs_bytes"],
                                        ubi_eb_size,
                                        ProduceHumanNumber(fs_bytes),
                                    )
                                )

                    if "fs_blocks" in part:
                        max_fs_blocks = (
                            part["bytes"] // metadata["fs_block_size"]
                        )
                        part["fs_blocks"] = ParseRelativeNumber(
                            max_fs_blocks, part["fs_blocks"]
                        )
                        part["fs_bytes"] = (
                            part["fs_blocks"] * metadata["fs_block_size"]
                        )
                        if part["fs_bytes"] % metadata["fs_align"] != 0:
                            raise InvalidSizeError(
                                'File system size: "%s" (%s bytes) is not an '
                                "even multiple of fs_align: %s"
                                % (
                                    part["fs_blocks"],
                                    part["fs_bytes"],
                                    metadata["fs_align"],
                                )
                            )

                        if part["fs_bytes"] > part["bytes"]:
                            raise InvalidLayoutError(
                                "Filesystem may not be larger than partition: "
                                "%s %s: %d > %d"
                                % (
                                    layout_name,
                                    part["label"],
                                    part["fs_bytes"],
                                    part["bytes"],
                                )
                            )
                    if "erase_block_size" in part:
                        part["erase_block_size"] = ParseHumanNumber(
                            part["erase_block_size"]
                        )
                    if "page_size" in part:
                        part["page_size"] = ParseHumanNumber(part["page_size"])

                    part.setdefault("features", [])
                    unknown_features = set(part["features"]) - valid_features
                    if unknown_features:
                        raise InvalidLayoutError(
                            "%s: Unknown features: %s"
                            % (part["label"], unknown_features)
                        )
        except KeyError as e:
            raise InvalidLayoutError(
                "Layout is missing required entries: %s" % e
            )

        return config

    def _getDiskLayoutPath(self) -> Union[os.PathLike, str]:
        """Get the disk layout file based on BOARD_OVERLAY.

        Returns:
            Disk layout path if exists or the legacy disk layout file path.
        """
        disk_layout = (
            constants.CROSUTILS_DIR / "build_library/legacy_disk_layout.json"
        )
        for overlay in os.environ.get("BOARD_OVERLAY", "").split():
            layout = Path(overlay) / "scripts/disk_layout.json"
            if layout.exists():
                disk_layout = layout
        return disk_layout

    def _getPartitionByNumber(
        self, partitions: Dict[Any, Any], num: int
    ) -> Dict[Any, Any]:
        """Given a partition table and number returns the partition object.

        Args:
            partitions: List of partitions to search in.
            num: Partition Number to find.

        Returns:
            An object for the selected partition.

        Raises:
            PartitionNotFoundError: If the partition is not found.
        """
        for partition in partitions:
            if partition.get("num") == num:
                return partition

        raise PartitionNotFoundError("Partition %d not found" % num)

    def _getPartitionsByType(
        self, partitions: Dict[Any, Any], typename: str
    ) -> List[Dict[Any, Any]]:
        """Given a partition table and type returns the partitions of the type.

        Partitions are sorted in num order.

        Args:
            partitions: List of partitions to search in.
            typename: The type of partitions to select.

        Returns:
            A list of partitions of the type.
        """
        out = []
        for partition in partitions:
            if partition.get("type") == typename:
                out.append(partition)
        return sorted(out, key=lambda partition: partition.get("num"))

    def _getMetadataPartition(
        self, partitions: Dict[Any, Any]
    ) -> Dict[Any, Any]:
        """Given a partition table returns the metadata partition object.

        Args:
            partitions: List of partitions to search in.

        Returns:
            An object for the metadata partition.
        """
        for partition in partitions:
            if partition.get("num") == "metadata":
                return partition

        return {}

    def _HasBadEraseBlocks(self, partitions: Dict[Any, Any]) -> bool:
        return "max_bad_erase_blocks" in self._getMetadataPartition(partitions)

    def _HasExternalGpt(self, partitions: Dict[Any, Any]) -> bool:
        """Returns True is 'external_gpt' property is defined in metadata.

        Args:
            partitions:
        """
        return self._getMetadataPartition(partitions).get("external_gpt", False)

    def _getPartitionByLabel(
        self, partitions: Dict[Any, Any], label: str
    ) -> Dict[Any, Any]:
        """Given a partition table and label returns the partition object.

        Args:
            partitions: List of partitions to search in.
            label: Label of partition to find.

        Returns:
            An object for the selected partition.

        Raises:
            PartitionNotFoundError: if the fiven label is not found.
        """
        for partition in partitions:
            if "label" not in partition:
                continue
            if partition["label"] == label:
                return partition

        raise PartitionNotFoundError('Partition "%s" not found' % label)

    def _applyPartitionAdjustment(
        self,
        partitions: Dict[Any, Any],
        metadata: Dict[Any, Any],
        label: str,
        operator: str,
        operand: str,
    ):
        """Applies an adjustment to a partition specified by label.

        Args:
            partitions: Partition table to modify.
            metadata: Partition table metadata.
            label: The label of the partition to adjust.
            operator: Type of adjustment (+/-/=).
            operand: How much to adjust by.

        Raises:
            ValueError: If the operand is invalid.
        """

        partition = self._getPartitionByLabel(partitions, label)

        operand_bytes = ParseHumanNumber(operand)

        if operator == "+":
            partition["bytes"] += operand_bytes
        elif operator == "-":
            partition["bytes"] -= operand_bytes
        elif operator == "=":
            partition["bytes"] = operand_bytes
        else:
            raise ValueError("unknown operator %s" % operator)

        if partition["type"] == "rootfs":
            # If we're adjusting a rootFS partition, we assume the full
            # partition size specified is being used for the filesystem,
            # minus the space reserved for the hashpad.
            partition["fs_bytes"] = partition["bytes"]
            partition["fs_blocks"] = (
                partition["fs_bytes"] // metadata["fs_block_size"]
            )
            # TODO(rchandrasekar): Document the need for 15% increase in size.
            partition["bytes"] = int(partition["bytes"] * 1.15)

    def _getPartitionTable(
        self, image_type: str, part_adjustments: Optional[List[str]] = None
    ) -> Dict[Any, Any]:
        """Generates requested image_type layout from a layout configuration.

        This loads the requested layout and applies the requested partition size
        adjustments. All the partition sizes will be in bytes.

        Args:
            image_type: Type of image eg base/test/dev/factory_install.
            part_adjustments: A list of partition size adjustments to apply.

        Returns:
            Object representing a selected partition table.

        Raises:
            InvalidLayoutError: If the layout is invalid.
            InvalidAdjustmentError: If the part_adjustments is invalid.
        """

        # We make a deep copy so that changes to the dictionaries in this list
        # do not persist across calls.
        partitions = copy.deepcopy(
            self._disk_layout_config["layouts"][image_type]
        )
        metadata = self._disk_layout_config["metadata"]

        # Convert fs_options from a dict to string.
        # fs_options can have multiple options for different filesystem formats.
        # Extract the fs_options applicable to this partition based on the
        # fs_format. Validate the fs_options value and update the partition
        # config dict.
        for partition in partitions:
            fs_options = partition.get("fs_options", "")
            if isinstance(fs_options, dict):
                fs_format = partition.get("fs_format")
                fs_options = fs_options.get(fs_format, "")
            elif not isinstance(fs_options, str):
                raise InvalidLayoutError(
                    "Partition number %s: fs_format must be a string or "
                    "dict, not %s" % (partition.get("num"), type(fs_options))
                )
            if '"' in fs_options or "'" in fs_options:
                raise InvalidLayoutError(
                    "Partition number %s: fs_format cannot have quotes"
                    % partition.get("num")
                )
            partition["fs_options"] = fs_options

        if not part_adjustments:
            return partitions

        for adjustment_str in part_adjustments:
            adjustment = adjustment_str.split(":")
            if len(adjustment) < 2:
                raise InvalidAdjustmentError(
                    'Adjustment "%s" is incomplete' % adjustment_str
                )

            label = adjustment[0]
            operator = adjustment[1][0]
            operand = adjustment[1][1:]
            self._applyPartitionAdjustment(
                partitions, metadata, label, operator, operand
            )

        return partitions

    def GetImageTypes(self) -> List[str]:
        """Returns a list of all the image types in the layout.

        Returns:
            List of all image types.
        """
        return self._disk_layout_config["layouts"].keys()

    def GetBlockSize(self) -> int:
        """Returns the partition table block size.

        Returns:
            Block size of all partitions in the layout.
        """

        return self._disk_layout_config["metadata"]["block_size"]

    def GetFilesystemBlockSize(self) -> int:
        """Returns the filesystem block size.

        This is used for all partitions in the table that have filesystems.

        Returns:
            Block size of all filesystems in the layout.
        """

        return self._disk_layout_config["metadata"]["fs_block_size"]

    def GetType(self, image_type: str, num: int) -> str:
        """Returns the type of a given partition for a given layout.

        Args:
            image_type: Type of image eg base/test/dev/factory_install.
            num: Partition Number.

        Returns:
            Type of the specified partition.

        Raises:
            PartitionNotFoundError: If the partition is not found.
            InvalidLayoutError: If the image type is not supported.
        """
        try:
            partitions = self._image_partitions[image_type]
        except KeyError:
            raise InvalidLayoutError("Unknown layout: %s" % image_type)
        partition = self._getPartitionByNumber(partitions, num)

        return partition.get("type")

    def GetPartitions(self, image_type: str) -> str:
        """Returns the partition numbers for the image_type.

        Args:
            image_type: Type of image eg base/test/dev/factory_install.
            layout_filename: Path to partition configuration file.

        Returns:
            A space delimited string of partition numbers.

        Raises:
            InvalidLayoutError: If the image type is not supported.
        """
        try:
            partitions = self._image_partitions[image_type]
        except KeyError:
            raise InvalidLayoutError("Unknown layout: %s" % image_type)

        return " ".join(
            str(p["num"])
            for p in partitions
            if "num" in p and p["num"] != "metadata"
        )

    def GetUUID(self, image_type: str, num: int) -> str:
        """Returns the filesystem UUID for a given layout type.

        Args:
            image_type: Type of image eg base/test/dev/factory_install.
            num: Number of the partition you want to read from.

        Returns:
            UUID of specified partition. Defaults to 'random' if not set.

        Raises:
            InvalidLayoutError: If the image type is not supported.
        """
        try:
            partitions = self._image_partitions[image_type]
        except KeyError:
            raise InvalidLayoutError("Unknown layout: %s" % image_type)
        partition = self._getPartitionByNumber(partitions, num)

        return partition.get("uuid", "random")

    def GetPartitionSize(self, image_type: str, num: int) -> int:
        """Returns the partition size for a given layout type.

        Args:
            image_type: Type of image eg base/test/dev/factory_install.
            num: Number of the partition you want to read from.

        Returns:
            Size of selected partition in bytes.

        Raises:
            InvalidLayoutError: If the image type is not supported.
        """

        try:
            partitions = self._image_partitions[image_type]
        except KeyError:
            raise InvalidLayoutError("Unknown layout: %s" % image_type)
        partition = self._getPartitionByNumber(partitions, num)

        return partition["bytes"]

    def GetFilesystemFormat(self, image_type: str, num: int) -> str:
        """Returns the filesystem format of a partition for a given layout type.

        Args:
            image_type: Type of image eg base/test/dev/factory_install.
            num: Number of the partition you want to read from.

        Returns:
            Format of the selected partition's filesystem.

        Raises:
            InvalidLayoutError: If the image type is not supported.
        """
        try:
            partitions = self._image_partitions[image_type]
        except KeyError:
            raise InvalidLayoutError("Unknown layout: %s" % image_type)
        partition = self._getPartitionByNumber(partitions, num)

        return partition.get("fs_format")

    def GetFormat(self, image_type: str, num: int) -> str:
        """Returns the format of a given partition for a given layout type.

        Args:
            image_type: Type of image eg base/test/dev/factory_install.
            num: Number of the partition you want to read from.

        Returns:
            Format of the selected partition's filesystem.

        Raises:
            InvalidLayoutError: If the image type is not supported.
        """
        try:
            partitions = self._image_partitions[image_type]
        except KeyError:
            raise InvalidLayoutError("Unknown layout: %s" % image_type)
        partition = self._getPartitionByNumber(partitions, num)

        return partition.get("format")

    def GetFilesystemOptions(self, image_type: str, num: int) -> str:
        """Returns the filesystem options of a given partition and layout type.

        Args:
            image_type: Type of image eg base/test/dev/factory_install.
            num: Number of the partition you want to read from.

        Returns:
            The selected partition's filesystem options.

        Raises:
            InvalidLayoutError: If the image type is not supported.
        """
        try:
            partitions = self._image_partitions[image_type]
        except KeyError:
            raise InvalidLayoutError("Unknown layout: %s" % image_type)
        partition = self._getPartitionByNumber(partitions, num)

        return partition.get("fs_options")

    def GetFilesystemSize(self, image_type: str, num: int) -> int:
        """Returns the filesystem size for a given layout type.

        If no filesystem size is specified, returns the partition size.

        Args:
            image_type: Type of image eg base/test/dev/factory_install.
            num: Number of the partition you want to read from.

        Returns:
            Size of selected partition filesystem in bytes.

        Raises:
            InvalidLayoutError: If the image type is not supported.
        """
        try:
            partitions = self._image_partitions[image_type]
        except KeyError:
            raise InvalidLayoutError("Unknown layout: %s" % image_type)
        partition = self._getPartitionByNumber(partitions, num)

        if "fs_bytes" in partition:
            return partition["fs_bytes"]
        else:
            return partition["bytes"]

    def GetLabel(self, image_type: str, num: int) -> str:
        """Returns the label for a given partition.

        Args:
            image_type: Type of image eg base/test/dev/factory_install.
            num: Number of the partition you want to read from.

        Returns:
            Label of selected partition, or 'UNTITLED' if none specified.

        Raises:
            InvalidLayoutError: If the image type is not supported.
        """
        try:
            partitions = self._image_partitions[image_type]
        except KeyError:
            raise InvalidLayoutError("Unknown layout: %s" % image_type)
        partition = self._getPartitionByNumber(partitions, num)

        if "label" in partition:
            return partition["label"]
        else:
            return "UNTITLED"

    def GetNumber(self, image_type: str, label: str) -> int:
        """Returns the partition number of a given label.

        Args:
            image_type: Type of image eg base/test/dev/factory_install.
            label: Number of the partition you want to read from

        Returns:
            The number of the partition corresponding to the label.

        Raises:
            InvalidLayoutError: If the image type is not supported.
        """
        try:
            partitions = self._image_partitions[image_type]
        except KeyError:
            raise InvalidLayoutError("Unknown layout: %s" % image_type)
        partition = self._getPartitionByLabel(partitions, label)

        return partition["num"]

    def GetReservedEraseBlocks(self, image_type: str, num: int) -> int:
        """Returns the number of erase blocks reserved in the partition.

        Args:
            image_type: Type of image eg base/test/dev/factory_install.
            num: Number of the partition you want to read from.

        Returns:
            Number of reserved erase blocks.

        Raises:
            InvalidLayoutError: If the image type is not supported.
        """
        try:
            partitions = self._image_partitions[image_type]
        except KeyError:
            raise InvalidLayoutError("Unknown layout: %s" % image_type)
        partition = self._getPartitionByNumber(partitions, num)

        if "reserved_erase_blocks" in partition:
            return partition["reserved_erase_blocks"]
        else:
            return 0

    def _DumpLayout(self, image_type: str):
        """Prints out a human readable disk layout in on-disk order.

        Args:
            image_type: Type of image e.g. base/test/dev/factory_install.

        Raises:
            InvalidLayoutError: If the image type is not supported.
        """
        try:
            partitions = self._image_partitions[image_type]
        except KeyError:
            logging.error("Unknown layout: %s", image_type)
            return

        label_len = max(len(x["label"]) for x in partitions if "label" in x)
        type_len = max(len(x["type"]) for x in partitions if "type" in x)

        msg = (
            "num:%4s label:%-*s type:%-*s size:%-10s fs_size:%-10s features:%s"
        )

        logging.info("\n%s Layout Data", image_type.upper())
        for partition in partitions:
            if partition.get("num") == "metadata":
                continue

            size = ProduceHumanNumber(partition["bytes"])
            if "fs_bytes" in partition:
                fs_size = ProduceHumanNumber(partition["fs_bytes"])
            else:
                fs_size = "auto"

            logging.info(
                msg,
                partition.get("num", "auto"),
                label_len,
                partition.get("label", ""),
                type_len,
                partition.get("type", ""),
                size,
                fs_size,
                partition.get("features", []),
            )

    def DoDebugOutput(self, image_type: str):
        """Prints out a human readable disk layout in on-disk order.

        Args:
            image_type: Type of image
              e.g.ALL/LIST/base/test/dev/factory_install.
        """
        if image_type == "LIST":
            logging.info(" ".join(self.GetImageTypes()))
            return

        # Print out non-layout options first.
        logging.info("Config Data")
        metadata_msg = "field:%-14s value:%s"
        for key in self._disk_layout_config.keys():
            if key not in ("layouts", "_comment"):
                logging.info(metadata_msg, key, self._disk_layout_config[key])

        if image_type == "ALL":
            for layout in self.GetImageTypes():
                self._DumpLayout(layout)
        else:
            self._DumpLayout(image_type)

    def _GetPrimaryEntryArrayPaddingBytes(self) -> str:
        """Return the start LBA of the primary partition entry array.

        Normally this comes after the primary GPT header but can be adjusted by
        setting the "primary_entry_array_padding_bytes" key under "metadata" in
        the config.

        Returns:
            The position of the primary partition entry array.
        """

        return self._disk_layout_config["metadata"].get(
            "primary_entry_array_padding_bytes", 0
        )

    def _GetPartitionStartByteOffset(self, partitions: Dict[Any, Any]) -> int:
        """Return the first usable location (LBA) for partitions.

        This value is the byte offset after the PMBR, the primary GPT header,
        and partition entry array.

        We round it up to 32K bytes to maintain the same layout as before in the
        normal (no padding between the primary GPT header and its partition
        entry array) case.

        Args:
            partitions: List of partitions to process

        Returns:
            A suitable byte offset for partitions.
        """

        if self._HasExternalGpt(partitions):
            # If the GPT is external, then the offset of the partitions' actual
            # data will be 0, and we don't need to make space at the beginning
            # for the GPT.
            return 0
        else:
            return START_SECTOR + self._GetPrimaryEntryArrayPaddingBytes()

    def GetTableTotals(self, partitions: Dict[Any, Any]) -> Dict[Any, Any]:
        """Calculates total sizes/counts for a partition table.

        Args:
            partitions: List of partitions to process

        Returns:
            Dict containing totals data
        """

        fs_block_align_losses = 0
        start_sector = self._GetPartitionStartByteOffset(partitions)
        ret = {
            "expand_count": 0,
            "expand_min": 0,
            "last_partition_count": 0,
            "byte_count": start_sector,
        }

        # Total up the size of all non-expanding partitions to get the minimum
        # required disk size.
        for partition in partitions:
            if partition.get("num") == "metadata":
                continue

            if (
                partition.get("type") in ("data", "rootfs")
                and partition["bytes"] > 1
            ):
                fs_block_align_losses += self._disk_layout_config["metadata"][
                    "fs_align"
                ]
            else:
                fs_block_align_losses += self._disk_layout_config["metadata"][
                    "fs_block_size"
                ]
            if "expand" in partition["features"]:
                ret["expand_count"] += 1
                ret["expand_min"] += partition["bytes"]
            else:
                ret["byte_count"] += partition["bytes"]
            if "last_partition" in partition["features"]:
                ret["last_partition_count"] += 1

        # Account for the secondary GPT header and table.
        ret["byte_count"] += SECONDARY_GPT_BYTES

        # At present, only one expanding partition is permitted.
        # Whilst it'd be possible to have two, we don't need this yet
        # and it complicates things, so it's been left out for now.
        if ret["expand_count"] > 1:
            raise InvalidLayoutError(
                "1 expand partition allowed, %d requested" % ret["expand_count"]
            )

        # Only one partition can be last on the disk.
        if ret["last_partition_count"] > 1:
            raise InvalidLayoutError(
                "Only one last partition allowed, %d requested"
                % ret["last_partition_count"]
            )

        # We lose some extra bytes from the alignment which are now not
        # considered in min_disk_size because partitions are aligned on the fly.
        # Adding fs_block_align_losses corrects for the loss.
        ret["min_disk_size"] = (
            ret["byte_count"] + ret["expand_min"] + fs_block_align_losses
        )

        return ret

    def GetFullPartitionSize(
        self, partition: Dict[Any, Any], metadata: Dict[Any, Any]
    ) -> int:
        """Get the size of partition including metadata/reserved space in bytes.

        The partition only has to be bigger for raw NAND devices. Formula:
        - Add UBI per-block metadata (2 pages) if partition is UBI
        - Round up to erase block size
        - Add UBI per-partition metadata (4 blocks) if partition is UBI
        - Add reserved erase blocks
        """

        erase_block_size = metadata.get("erase_block_size", 0)
        size = partition["bytes"]

        if erase_block_size == 0:
            return size

        # See "Flash space overhead" in
        # http://www.linux-mtd.infradead.org/doc/ubi.html
        # for overhead calculations.
        is_ubi = partition.get("format") == "ubi"
        reserved_erase_blocks = partition.get("reserved_erase_blocks", 0)
        page_size = metadata.get("page_size", 0)

        if is_ubi:
            ubi_block_size = erase_block_size - 2 * page_size
            erase_blocks = (size + ubi_block_size - 1) // ubi_block_size
            size += erase_blocks * 2 * page_size

        erase_blocks = (size + erase_block_size - 1) // erase_block_size
        size = erase_blocks * erase_block_size

        if is_ubi:
            size += erase_block_size * 4

        size += reserved_erase_blocks * erase_block_size
        return size

    def WriteLayoutFunction(self, slines: str, func: str, image_type: str):
        """Writes a shell script function to write out a given partition table.

        Args:
            slines: lines to write to the script
            func: function of the layout:
                for removable storage device: 'partition',
                for the fixed storage device: 'base'
            image_type: Type of image eg base/test/dev/factory_install
        """

        gpt_add = (
            "${GPT} add -i %d -b $(( curr / block_size )) "
            + '-s ${blocks} -t %s -l "%s" ${target}'
        )
        try:
            partitions = self._image_partitions[image_type]
        except KeyError:
            raise InvalidLayoutError("Unknown layout: %s" % image_type)
        metadata = self._getMetadataPartition(partitions)
        partition_totals = self.GetTableTotals(partitions)
        fs_align_snippet = [
            "if [ $(( curr %% %d )) -gt 0 ]; then"
            % self._disk_layout_config["metadata"]["fs_align"],
            "  : $(( curr += %d - curr %% %d ))"
            % ((self._disk_layout_config["metadata"]["fs_align"],) * 2),
            "fi",
        ]

        lines = [
            "write_%s_table() {" % func,
        ]

        if self._HasExternalGpt(partitions):
            # Read GPT from device to get size, then wipe it out and operate
            # on GPT in tmpfs. We don't rely on cgpt's ability to deal
            # directly with the GPT on SPI NOR flash because rewriting the
            # table so many times would take a long time (>30min).
            # Also, wiping out the previous GPT with create_image won't work
            # for NAND and there's no equivalent via cgpt.
            lines += [
                "gptfile=$(mktemp)",
                "flashrom -r -iRW_GPT:${gptfile}",
                "gptsize=$(stat ${gptfile} --format %s)",
                "dd if=/dev/zero of=${gptfile} bs=${gptsize} count=1",
                'target="-D %d ${gptfile}"' % metadata["bytes"],
            ]
        else:
            lines += [
                'local target="$1"',
                'create_image "${target}" %d'
                % partition_totals["min_disk_size"],
            ]

        lines += [
            "local blocks",
            'block_size=$(blocksize "${target}")',
            'numsecs=$(numsectors "${target}")',
        ]

        # ${target} is referenced unquoted because it may expand into multiple
        # arguments in the case of NAND
        lines += [
            "local curr=%d" % self._GetPartitionStartByteOffset(partitions),
            "# Make sure Padding is block_size aligned.",
            "if [ $(( %d & (block_size - 1) )) -gt 0 ]; then"
            % self._GetPrimaryEntryArrayPaddingBytes(),
            '  echo "Primary Entry Array padding is not block aligned." >&2',
            "  exit 1",
            "fi",
            "# Create the GPT headers and tables. Pad the primary ones.",
            "${GPT} create -p $(( %d / block_size )) ${target}"
            % self._GetPrimaryEntryArrayPaddingBytes(),
        ]

        metadata = self._getMetadataPartition(partitions)
        stateful = None
        last_part = None
        # Set up the expanding partition size and write out all the cgpt add
        # commands.
        for partition in partitions:
            if partition.get("num") == "metadata":
                continue

            partition["var"] = self.GetFullPartitionSize(partition, metadata)
            if "expand" in partition["features"]:
                stateful = partition
                continue

            # Save the last partition to place at the end of the disk..
            if "last_partition" in partition["features"]:
                last_part = partition
                continue

            if (
                partition.get("type") in ["data", "rootfs"]
                and partition["bytes"] > 1
            ):
                lines += fs_align_snippet

            if partition["var"] != 0 and partition.get("num") != "metadata":
                lines += [
                    "blocks=$(( %s / block_size ))" % partition["var"],
                    "if [ $(( %s %% block_size )) -gt 0 ]; then"
                    % partition["var"],
                    "   : $(( blocks += 1 ))",
                    "fi",
                ]

            if partition["type"] != "blank":
                lines += [
                    gpt_add
                    % (partition["num"], partition["type"], partition["label"]),
                ]

            # Increment the curr counter ready for the next partition.
            if partition["var"] != 0 and partition.get("num") != "metadata":
                lines += [
                    ": $(( curr += blocks * block_size ))",
                ]

        if stateful is not None:
            lines += fs_align_snippet + [
                "blocks=$(( numsecs - (curr + %d) / block_size ))"
                % SECONDARY_GPT_BYTES,
            ]
            if last_part is not None:
                lines += [
                    "reserved_blocks=$(( (%s + block_size - 1) / block_size ))"
                    % last_part["var"],
                    ": $(( blocks = blocks - reserved_blocks ))",
                ]
            lines += [
                gpt_add
                % (stateful["num"], stateful["type"], stateful["label"]),
                ": $(( curr += blocks * block_size ))",
            ]

        if last_part is not None:
            lines += [
                "reserved_blocks=$(( (%s + block_size - 1) / block_size ))"
                % last_part["var"],
                "blocks=$((reserved_blocks))",
                gpt_add
                % (last_part["num"], last_part["type"], last_part["label"]),
            ]

        # Set default priorities and retry counter on kernel partitions.
        tries = 15
        prio = 15
        # The order of partition numbers in this loop matters.
        # Make sure partition #2 is the first one, since it will be marked as
        # default bootable partition.
        for partition in self._getPartitionsByType(partitions, "kernel"):
            lines += [
                "${GPT} add -i %s -S 0 -T %i -P %i ${target}"
                % (partition["num"], tries, prio)
            ]
            prio = 0
            # When not writing 'base' function, make sure the other partitions
            # are marked as non-bootable (retry count == 0), since the USB
            # layout doesn't have any valid data in slots B & C. But with base
            # function, called by chromeos-install script, the KERNEL A
            # partition is replicated into both slots A & B, so we should leave
            # both bootable for error recovery in this case.
            if func != "base":
                tries = 0

        efi_partitions = self._getPartitionsByType(partitions, "efi")
        if efi_partitions:
            lines += [
                "${GPT} boot -p -b $2 -i %d ${target}"
                % efi_partitions[0]["num"],
                "${GPT} add -i %s -B 1 ${target}" % efi_partitions[0]["num"],
            ]
        else:
            # Provide a PMBR all the time for boot loaders (like u-boot)
            # that expect one to always be there.
            lines += [
                "${GPT} boot -p -b $2 ${target}",
            ]

        if metadata.get("hybrid_mbr"):
            # TODO(b/302183858): The viking board is using type=firmware
            # instead of type=efi for the efi partition.
            if not efi_partitions:
                efi_partitions = self._getPartitionsByType(
                    partitions, "firmware"
                )
            lines += [
                "install_hybrid_mbr ${target} %d" % efi_partitions[0]["num"]
            ]
        lines += ["${GPT} show ${target}"]

        if self._HasExternalGpt(partitions):
            lines += ["flashrom -w -iRW_GPT:${gptfile} --noverify-all"]

        slines += "%s\n}\n\n" % "\n  ".join(lines)

    def WritePartitionSizesFunction(
        self, slines: str, func: str, image_type: str, data: Dict[Any, Any]
    ):
        """Writes the partition size variable that can be extracted by a caller.

        Args:
            slines: lines to write to the script file.
            func: function of the layout:
                for removable storage device: 'partition',
                for the fixed storage device: 'base'.
            image_type: Type of image eg base/test/dev/factory_install.
            data: data dict we will write to a json file.
        """
        func_name = "load_%s_vars" % func
        lines = [
            "%s() {" % func_name,
            'DEFAULT_ROOTDEV="%s"'
            % self._disk_layout_config["metadata"].get("rootdev_%s" % func, ""),
        ]

        data[func_name] = {}
        data[func_name]["DEFAULT_ROOTDEV"] = "%s" % self._disk_layout_config[
            "metadata"
        ].get("rootdev_%s" % func, "")

        try:
            partitions = self._image_partitions[image_type]
        except KeyError:
            raise InvalidLayoutError("Unknown layout: %s" % image_type)
        for partition in partitions:
            if partition.get("num") == "metadata":
                continue
            for key in ("label", "num"):
                if key in partition:
                    shell_label = str(partition[key]).replace("-", "_").upper()
                    part_bytes = partition["bytes"]
                    reserved_ebs = partition.get("reserved_erase_blocks", 0)
                    fs_bytes = partition.get("fs_bytes", part_bytes)
                    part_format = partition.get("format", "")
                    fs_format = partition.get("fs_format", "")
                    fs_options = partition.get("fs_options", "")
                    partition_num = partition.get("num", "")
                    args = [
                        ("PARTITION_SIZE_", part_bytes),
                        ("RESERVED_EBS_", reserved_ebs),
                        ("DATA_SIZE_", fs_bytes),
                        ("FORMAT_", part_format),
                        ("FS_FORMAT_", fs_format),
                    ]
                    sargs = [
                        ("FS_OPTIONS_", fs_options),
                        ("PARTITION_NUM_", partition_num),
                    ]
                    for arg, value in args:
                        label = arg + shell_label
                        lines += [
                            "%s=%s" % (label, value),
                        ]
                        data[func_name][label] = "%s" % value
                    for arg, value in sargs:
                        label = arg + shell_label
                        lines += [
                            '%s="%s"' % (label, value),
                        ]
                        data[func_name][label] = "%s" % value
        slines += "%s\n}\n\n" % "\n  ".join(lines)

    def WritePartitionScript(
        self,
        image_type: str,
        sfilename: Union[str, os.PathLike],
        vfilename: Union[str, os.PathLike],
    ):
        """Writes shell script with functions for 'base' and requested layouts.

        Args:
            image_type: Type of image eg base/test/dev/factory_install
            sfilename: Filename to write the finished script to
            vfilename: Filename to write the partition variables json data to
        """
        with open(sfilename, "w", encoding="utf-8") as f:
            script_shell = GetScriptShell()
            f.write(script_shell)

            data = {}
            slines = []
            for func, layout in (
                ("base", BASE_LAYOUT),
                ("partition", image_type),
            ):
                self.WriteLayoutFunction(slines, func, layout)
                self.WritePartitionSizesFunction(slines, func, layout, data)

            f.write("".join(slines))
            with open(vfilename, "w", encoding="utf-8") as jFile:
                json.dump(data, jFile)

            # TODO: Backwards compat.  Should be killed off once we update
            #       cros_generate_update_payload to use the new code.
            try:
                partitions = self._image_partitions[BASE_LAYOUT]
            except KeyError:
                raise InvalidLayoutError("Unknown layout: %s" % image_type)
            partition = self._getPartitionByLabel(partitions, "ROOT-A")
            f.write("ROOTFS_PARTITION_SIZE=%s\n" % (partition["bytes"],))

    def CheckRootfsPartitionsMatch(self, partitions: Dict[Any, Any]):
        """Checks that rootfs partitions are substitutable with each other.

        This function asserts that either all rootfs partitions are in the same
        format or none have a format, and it asserts that have the same number
        of reserved erase blocks.

        Args:
            partitions: The partition to validate.

        Raises:
            MismatchedRootfsFormatError: If partition format mismatch.
            MismatchedRootfsBlocksError: If reserved erase block mismatch.
        """
        partition_format = None
        reserved_erase_blocks = -1
        for partition in partitions:
            if partition.get("type") == "rootfs":
                new_format = partition.get("format", "")
                new_reserved_erase_blocks = partition.get(
                    "reserved_erase_blocks", 0
                )

                if partition_format is None:
                    partition_format = new_format
                    reserved_erase_blocks = new_reserved_erase_blocks

                if new_format != partition_format:
                    raise MismatchedRootfsFormatError(
                        'mismatched rootfs formats: "%s" and "%s"'
                        % (partition_format, new_format)
                    )

                if reserved_erase_blocks != new_reserved_erase_blocks:
                    raise MismatchedRootfsBlocksError(
                        "mismatched rootfs reserved erase block counts: i"
                        "%s and %s"
                        % (reserved_erase_blocks, new_reserved_erase_blocks)
                    )

    def CheckReservedEraseBlocks(self, partitions: Dict[Any, Any]):
        """Checks that the reserved_erase_blocks in each partition is good.

        This function checks that a reasonable value was given for the reserved
        erase block count. In particular, it checks that there's a less than
        1 in 100k probability that, if the manufacturer's maximum bad erase
        block count is met, and assuming bad blocks are uniformly randomly
        distributed, then more bad blocks will fall in this partition than are
        reserved. Smaller partitions need a larger reserve percentage.

        We take the number of reserved blocks as a parameter in disk_layout.json
        rather than just calculating the value so that it can be tweaked
        explicitly along with others in squeezing the image onto flash. But
        we check it so that users have an easy method for determining what's
        acceptable--just try out a new value and do `cros build-image`.

        Args:
            partitions: The partition to validate.

        Raises:
            ExcessFailureProbabilityError: If excessive probablity exists for
                failure.
            MissingEraseBlockFieldError: If unable to check for erased blocks.
        """
        for partition in partitions:
            if "reserved_erase_blocks" in partition or partition.get(
                "format"
            ) in (
                "ubi",
                "nand",
            ):
                if partition.get("bytes", 0) == 0:
                    continue
                metadata = self._getMetadataPartition(partitions)
                if (
                    not self._HasBadEraseBlocks(partitions)
                    or "reserved_erase_blocks" not in partition
                    or "bytes" not in metadata
                    or "erase_block_size" not in metadata
                    or "page_size" not in metadata
                ):
                    raise MissingEraseBlockFieldError(
                        "unable to check if partition %s will have too many "
                        "bad blocks due to missing metadata field"
                        % partition["label"]
                    )

                reserved = partition["reserved_erase_blocks"]
                erase_block_size = metadata["erase_block_size"]
                device_erase_blocks = metadata["bytes"] // erase_block_size
                device_bad_blocks = metadata["max_bad_erase_blocks"]
                distributions = Combinations(
                    device_erase_blocks, device_bad_blocks
                )
                partition_erase_blocks = partition["bytes"] // erase_block_size
                # The idea is to calculate the number of ways that there could
                # be reserved or more bad blocks inside the partition, assuming
                # that there are device_bad_blocks in the device in total
                # (the worst case). To get the probability, we divide this
                # count by the total number of ways that the bad blocks can be
                # distribute on the whole device. To find the first number, we
                # sum over increasing values for the count of bad blocks within
                # the partition the number of ways that those bad blocks can be
                # inside the partition, multiplied by the number of ways that
                # the remaining blocks can be distributed outside of the
                # partition.
                ways_for_failure = sum(
                    Combinations(partition_erase_blocks, partition_bad_blocks)
                    * Combinations(
                        device_erase_blocks - partition_erase_blocks,
                        device_bad_blocks - partition_bad_blocks,
                    )
                    for partition_bad_blocks in range(
                        reserved + 1, device_bad_blocks + 1
                    )
                )
                probability = ways_for_failure / distributions
                if probability > 0.00001:
                    raise ExcessFailureProbabilityError(
                        "excessive probability %f of too many "
                        "bad blocks in partition %s"
                        % (probability, partition["label"])
                    )

    def CheckSimpleNandProperties(self, partitions: Dict[Any, Any]):
        """Checks that NAND partitions are erase-block-aligned and not expand.

        Args:
            partitions: The partition to validate.

        Raises:
            UnalignedPartitionError: if the partition size is not aligned with
                erase block size.
            ExpandNandImpossibleError: If expand partition is specified for
                NAND.
        """
        if not self._HasBadEraseBlocks(partitions):
            return
        metadata = self._getMetadataPartition(partitions)
        erase_block_size = metadata["erase_block_size"]
        for partition in partitions:
            if partition["bytes"] % erase_block_size != 0:
                raise UnalignedPartitionError(
                    "partition size %s does not divide erase block size %s"
                    % (partition["bytes"], erase_block_size)
                )
            if "expand" in partition["features"]:
                raise ExpandNandImpossibleError(
                    "expand partitions may not be used with raw NAND"
                )

    def CheckTotalSize(self, partitions: Dict[Any, Any]):
        """Checks that the sum size of all partitions fits within the device.

        Args:
            partitions: The partition to evaluate.

        Raises:
            ExcessPartitionSizeError: if the total partition size is greater
                than the capacity.
        """
        metadata = self._getMetadataPartition(partitions)
        if "bytes" not in metadata:
            return
        capacity = metadata["bytes"]
        total = sum(
            self.GetFullPartitionSize(partition, metadata)
            for partition in partitions
            if partition.get("num") != "metadata"
        )
        if total > capacity:
            raise ExcessPartitionSizeError(
                "capacity = %d, total=%d" % (capacity, total)
            )

    def Validate(self, image_type: str):
        """Validates a layout file.

        Args:
            image_type: Type of image eg base/test/dev/factory_install.

        Raises:
            ExcessPartitionSizeError: if the total partition size is greater
                than the capacity.
            UnalignedPartitionError: if the partition size is not aligned with
                erase block size.
            ExpandNandImpossibleError: If expand partition is specified for
                NAND.
            ExcessFailureProbabilityError: If excessive probablity exists for
                failure.
            MissingEraseBlockFieldError: If unable to check for erased blocks.
            MismatchedRootfsFormatError: If partition format mismatch.
            MismatchedRootfsBlocksError: If reserved erase block mismatch.
            InvalidLayoutError: If the image type is invalid.
        """
        try:
            partitions = self._image_partitions[image_type]
        except KeyError:
            raise InvalidLayoutError("Unknown layout: %s" % image_type)
        self.CheckRootfsPartitionsMatch(partitions)
        self.CheckTotalSize(partitions)
        self.CheckSimpleNandProperties(partitions)
        self.CheckReservedEraseBlocks(partitions)
