# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the repo_manifest module."""

import pytest

from chromite.format.formatters import repo_manifest


# None means input is already formatted to avoid having to repeat.
TEST_CASES = (
    (
        """<?xml version="1.0" encoding="UTF-8"?>
<manifest/>
""",
        None,
    ),
    # Project element without children is collapsed.
    (
        """<?xml version="1.0" encoding="UTF-8"?>
<manifest>
  <project path="path"
           name="name">
  </project>
</manifest>
""",
        """<?xml version="1.0" encoding="UTF-8"?>
<manifest>
  <project path="path"
           name="name" />

</manifest>
""",
    ),
    # Multiple newlines are collapsed.
    (
        """<?xml version="1.0" encoding="UTF-8"?>
<manifest>
  <project path="path"
           name="name" />


  <project path="path"
           name="name" />
</manifest>
""",
        """<?xml version="1.0" encoding="UTF-8"?>
<manifest>
  <project path="path"
           name="name" />

  <project path="path"
           name="name" />
</manifest>
""",
    ),
    # Comments are indented correctly.
    (
        """<?xml version="1.0" encoding="UTF-8"?>
<!-- yes
       too much
no
\t
maybe -->
<!--x-->
<manifest></manifest>
""",
        """<?xml version="1.0" encoding="UTF-8"?>
<!-- yes
     too much
     no

     maybe -->
<!-- x -->
<manifest/>
""",
    ),
    (
        """<?xml version="1.0" encoding="UTF-8"?>
<!--
-->
<!--

-->
<!-- --><manifest/>""",
        """<?xml version="1.0" encoding="UTF-8"?>
<!--  -->
<!--  -->
<!--  -->
<manifest/>
""",
    ),
)


# Use a separate variable to avoid pytest log spam.
@pytest.mark.parametrize("data,exp", TEST_CASES)
def test_check_format(data, exp):
    """Verify inputs match expected outputs."""
    if exp is None:
        exp = data
    assert exp == repo_manifest.Data(data)
