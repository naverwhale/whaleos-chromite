# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Script to generate (+ upload) DLC artifacts."""

import logging
import os
import shutil
from typing import List

from chromite.lib import commandline
from chromite.lib import cros_build_lib
from chromite.lib import dlc_lib
from chromite.lib import osutils


# Predefined salts.
_SHORT_SALT = "1337D00D"

# Tarball extension with correct compression.
_TAR_COMP_EXT = ".tar.zst"
_META_OUT_FILE = dlc_lib.DLC_TMP_META_DIR + _TAR_COMP_EXT

# Filenames.
_METADATA_FILE = "metadata"


def ParseArguments(argv: List[str]) -> commandline.ArgumentNamespace:
    """Returns a namespace for the CLI arguments."""
    parser = commandline.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--src-dir",
        type="dir_exists",
        required=True,
        help="The directory to package as a DLC",
    )
    # Support license addition here. For now, have users explicitly pass in a
    # stub license path.
    parser.add_argument(
        "--license",
        type="file_exists",
        required=True,
        help="The path to license, this should be the same license as the one"
        " used within the package",
    )
    parser.add_argument(
        "--output-dir",
        type="path",
        help="The optional output directory to put artifacts into",
    )
    parser.add_argument(
        "--output-metadata-dir",
        type="path",
        help="The optional output directory to put metadata into",
    )

    parser.add_bool_argument(
        "--upload",
        default=False,
        enabled_desc="Upload the DLC artifacts to google buckets",
        disabled_desc="Do not upload the DLC artifacts to google buckets",
    )
    parser.add_argument(
        "--uri-path",
        type="gs_path",
        help="The override for DLC image URI, check dlc_lib for default",
    )
    parser.add_bool_argument(
        "--upload-dry-run",
        default=False,
        enabled_desc="Dry run without actual upload",
        disabled_desc="Ignored",
    )

    parser.add_bool_argument(
        "--reproducible-image",
        default=False,
        enabled_desc="To generate reproducible DLC images",
        disabled_desc="To generate randomized DLC images",
    )

    # Enable powerwash safety for this DLC.
    parser.add_bool_argument(
        "--powerwash-safety",
        default=False,
        enabled_desc="Enable powerwash safety feature for this DLC",
        disabled_desc="Disable powerwash safety feature for this DLC",
    )

    # DLC required fields.
    parser.add_argument(
        "--id",
        type=str,
        required=True,
        help="The DLC ID",
    )
    parser.add_argument(
        "--preallocated-blocks",
        type=int,
        required=True,
        help="The preallocated number of blocks in 4KiB chunks",
    )

    # DLC optional fields.
    parser.add_argument(
        "--name",
        type=str,
        default="",
        help="The name of the DLC in human friendly format",
    )
    parser.add_argument(
        "--description",
        type=str,
        default="",
        help="The description of the DLC in human friendly format",
    )
    parser.add_argument(
        "--version",
        type=str,
        required=True,
        help="The version of this DLC build",
    )

    opts = parser.parse_args(argv)

    dlc_lib.ValidateDlcIdentifier(opts.id)

    opts.Freeze()

    return opts


def GenerateDlcParams(
    opts: commandline.ArgumentNamespace,
) -> dlc_lib.EbuildParams:
    """Generates and verifies DLC parameters based on options

    Args:
        opts: The command line arguments.

    Returns:
        The DLC ebuild parameters.
    """
    params = dlc_lib.EbuildParams(
        dlc_id=opts.id,
        dlc_package="package",
        fs_type=dlc_lib.SQUASHFS_TYPE,
        pre_allocated_blocks=opts.preallocated_blocks,
        version=opts.version,
        name=opts.name,
        description=opts.description,
        # Add preloading support.
        preload=False,
        used_by="",
        mount_file_required=False,
        fullnamerev="",
        scaled=True,
        loadpin_verity_digest=False,
        powerwash_safe=opts.powerwash_safety,
        use_logical_volume=True,
    )
    params.VerifyDlcParameters()
    return params


def UploadDlcArtifacts(
    dlcartifacts: dlc_lib.DlcArtifacts, dry_run: bool
) -> None:
    """Uploads the DLC artifacts based on `DlcArtifacts`

    Args:
        dlcartifacts: The DLC artifacts to upload.
        dry_run: Dry run without actually uploading if true.
    """
    logging.info("Uploading DLC artifacts")
    logging.debug(
        "Uploading DLC image %s to %s",
        dlcartifacts.image,
        dlcartifacts.uri_path,
    )
    logging.debug(
        "Uploading DLC meta %s to %s", dlcartifacts.meta, dlcartifacts.uri_path
    )
    dlcartifacts.Upload(dry_run=dry_run)


def GenerateDlcArtifacts(opts: commandline.ArgumentNamespace) -> None:
    """Generates the DLC artifacts

    Args:
        opts: The command line arguments.
    """
    params = GenerateDlcParams(opts)
    uri_path = opts.uri_path or params.GetUriPath()

    with osutils.TempDir(prefix="dlcartifacts", sudo_rm=True) as tmpdir:
        output_dir = opts.output_dir or tmpdir
        os.makedirs(output_dir, exist_ok=True)

        logging.info("Generating DLC artifacts")
        artifacts = dlc_lib.DlcGenerator(
            src_dir=opts.src_dir,
            sysroot="",
            board=dlc_lib.MAGIC_BOARD,
            ebuild_params=params,
            reproducible=opts.reproducible_image,
            license_file=opts.license,
        ).ExternalGenerateDLC(
            tmpdir, _SHORT_SALT if opts.reproducible_image else None
        )
        logging.debug("Generated DLC artifacts: %s", artifacts.StringJSON())

        # Handle the meta.
        meta_out = os.path.join(output_dir, _META_OUT_FILE)

        logging.info("Emitting the metadata into %s", meta_out)
        cros_build_lib.CreateTarball(
            tarball_path=meta_out,
            cwd=artifacts.meta,
            compression=cros_build_lib.CompressionType.ZSTD,
            extra_env={"ZSTD_CLEVEL": "9"},
        )

        # Handle the image.
        image_out = os.path.join(output_dir, dlc_lib.DLC_IMAGE)
        logging.info("Emitting the DLC image into %s", image_out)
        shutil.move(artifacts.image, image_out)

        # Handle the upload.
        ret_artifacts = dlc_lib.DlcArtifacts(
            uri_path=uri_path,
            image=image_out,
            meta=meta_out,
        )
        ret_artifacts_json = ret_artifacts.StringJSON()
        logging.debug("The final DLC artifacts: %s", ret_artifacts_json)

        if opts.output_metadata_dir:
            osutils.WriteFile(
                os.path.join(opts.output_metadata_dir, _METADATA_FILE),
                ret_artifacts_json,
                makedirs=True,
            )

        if opts.upload or opts.upload_dry_run:
            UploadDlcArtifacts(ret_artifacts, opts.upload_dry_run)
        else:
            logging.debug("Skipping DLC artifacts upload")


def main(argv):
    GenerateDlcArtifacts(ParseArguments(argv))
