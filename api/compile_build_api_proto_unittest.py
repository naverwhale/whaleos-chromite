# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""compile_build_api_proto tests."""

import os

from chromite.third_party.google import protobuf

from chromite.api import compile_build_api_proto


def test_versions_match():
    """Verify the versions match.

    The protoc version in the compile script needs to be compatible with the
    version of the library we're using (in chromite/third_party). For now, that
    means we're checking equality.

    TODO: Investigate whether, e.g. 1.2.0 ~= 1.2.3, and we only need to check
        the major and minor components.
    TODO: Investigate using protobuf.__version__ instead of hard coding a
        version in compile_build_api_proto.
    """
    assert (
        f"{compile_build_api_proto.PROTOC_MAJOR_VERSION}."
        f"{compile_build_api_proto.PROTOC_VERSION}"
    ) == protobuf.__version__, (
        "The protobuf library or compile_build_api_proto.PROTOC_VERSION has "
        "been updated, but the other has not. They must be updated together."
    )


def test_compiles(tmpdir):
    """Test the script successfully compiles something."""
    assert not os.listdir(tmpdir)
    compile_build_api_proto.main(["--destination", str(tmpdir)])
    # It may produce an __init__.py even if nothing else succeeded, so make sure
    # we have more than just that.
    assert len(os.listdir(tmpdir)) > 1
