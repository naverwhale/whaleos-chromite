# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test chromite.lib.disk_layout"""

import os

from chromite.lib import constants
from chromite.lib import cros_test_lib
from chromite.lib import disk_layout
from chromite.lib import osutils


class JSONLoadingTest(cros_test_lib.MockTempDirTestCase):
    """Test stacked JSON loading functions."""

    def setUp(self):
        self.layout_json = os.path.join(self.tempdir, "test_layout.json")
        self.parent_layout_json = os.path.join(
            self.tempdir, "test_layout_parent.json"
        )
        self.another_parent_layout_json = os.path.join(
            self.tempdir, "test_layout_another_parent.json"
        )
        self.parent_layout_content = """{
          "metadata": {
            "fs_block_size": 4096
          },
          "layouts": {
              "base": [
                {
                  "num": 3,
                  "label": "Part 3",
                  "type": "rootfs"
                },
                {
                  "num": 2,
                  "label": "Part 2",
                  "type": "data"
                },
                {
                  "num": 1,
                  "label": "Part 1",
                  "type": "efi"
                }
              ]
            }
          }"""

    def testJSONComments(self):
        """Test that we ignore comments in JSON in lines starting with #."""
        osutils.WriteFile(
            self.layout_json,
            """# This line is a comment.
                {
                    #  comment with some whitespaces on the left.
                    "metadata": {
                        "fs_block_size": 4096
                    },
                    "layouts": {
                        "common": [],
                        "base": []
                    }
                }
                """,
        )

        layout = disk_layout.DiskLayout(self.layout_json)
        # pylint: disable-msg=W0212
        self.assertEqual(
            layout._disk_layout_config,
            {
                "metadata": {"fs_block_size": 4096, "fs_align": 4096},
                "layouts": {"common": [], "base": []},
            },
        )

    def testJSONCommentsLimitations(self):
        """Test that we can't parse inline comments in JSON.

        If we ever enable this, we need to change the README.disk_layout
        documentation to mention it.
        """
        osutils.WriteFile(
            self.layout_json,
            """{
                    "layouts": { # This is an inline comment.
                        "common": []
                    }
                }""",
        )
        self.assertRaises(
            ValueError,
            disk_layout.DiskLayout,
            self.layout_json,
        )

    def testPartitionOrderPreserved(self):
        """Test the order of the partitions is the same as in the parent."""
        osutils.WriteFile(self.parent_layout_json, self.parent_layout_content)

        parent_layout = disk_layout.DiskLayout(self.parent_layout_json)

        osutils.WriteFile(
            self.layout_json,
            """{
                  "parent": "%s",
                  "layouts": {
                    "base": []
                  }
                }"""
            % self.parent_layout_json,
        )
        layout = disk_layout.DiskLayout(self.layout_json)
        # pylint: disable-msg=W0212
        self.assertEqual(
            parent_layout._disk_layout_config, layout._disk_layout_config
        )

        # Test also that even overriding one partition keeps all of them in
        # order.
        osutils.WriteFile(
            self.layout_json,
            """{
                  "parent": "%s",
                  "layouts": {
                    "base": [
                      {
                        "num": 2,
                        "label": "Part 2"
                      }
                    ]
                  }
                }"""
            % self.parent_layout_json,
        )
        layout = disk_layout.DiskLayout(self.layout_json)
        # pylint: disable-msg=W0212
        self.assertEqual(
            parent_layout._disk_layout_config, layout._disk_layout_config
        )

    def testJSONEmptyParent(self):
        """Test that absence of layout section in parent is supported."""
        osutils.WriteFile(self.parent_layout_json, "{}")
        osutils.WriteFile(
            self.layout_json,
            """{
                  "parent": "%s",
                  "metadata": {
                    "fs_block_size": 4096
                  },
                  "layouts": {
                    "base": [
                      {
                        "num": 2,
                        "label": "Part 2",
                        "type": "rootfs"
                      }
                    ]
                  }
                }"""
            % self.parent_layout_json,
        )
        disk_layout.DiskLayout(self.layout_json)

    def testJSONEmptyLayout(self):
        """Test that absence of layout section in child is supported."""
        osutils.WriteFile(self.parent_layout_json, self.parent_layout_content)

        parent_layout = disk_layout.DiskLayout(self.parent_layout_json)

        osutils.WriteFile(
            self.layout_json,
            """{
                  "parent": "%s"
                }"""
            % self.parent_layout_json,
        )
        layout = disk_layout.DiskLayout(self.layout_json)
        # pylint: disable-msg=W0212
        self.assertEqual(
            parent_layout._disk_layout_config, layout._disk_layout_config
        )

    def testJSONrequiredFields(self):
        """Test required fields."""
        # Need Metadata field.
        osutils.WriteFile(self.layout_json, "{}")

        with self.assertRaisesRegex(
            disk_layout.InvalidLayoutError,
            "Layout is missing required entries: " "'metadata'",
        ):
            disk_layout.DiskLayout(self.layout_json)

        # Need fs_block_size in Metadata.
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {}
                }""",
        )

        with self.assertRaisesRegex(
            disk_layout.InvalidLayoutError,
            "Layout is missing required entries: " "'fs_block_size'",
        ):
            disk_layout.DiskLayout(self.layout_json)

        # Need base layout.
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "fs_block_size": 4096
                  },
                  "layouts": {}
                }""",
        )

        with self.assertRaisesRegex(
            disk_layout.InvalidLayoutError, 'Missing "base" config.*'
        ):
            disk_layout.DiskLayout(self.layout_json)
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "fs_block_size": 4096
                  },
                  "layouts": {
                    "common": []
                  }
                }""",
        )

        with self.assertRaisesRegex(
            disk_layout.InvalidLayoutError, 'Missing "base" config.*'
        ):
            disk_layout.DiskLayout(self.layout_json)

    def testJSONPartitionRequiredFields(self):
        """Test partition required fields."""
        # Need partition type.
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "fs_block_size": 4096
                  },
                  "layouts": {
                    "base": [
                      {
                        "num": 1
                      }
                    ]
                  }
                }""",
        )

        with self.assertRaisesRegex(
            disk_layout.InvalidLayoutError,
            "Layout is missing required entries: " "'type'",
        ):
            disk_layout.DiskLayout(self.layout_json)

        # Need partition label.
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "fs_block_size": 4096
                  },
                  "layouts": {
                    "base": [
                      {
                        "num": 1,
                        "type": "data"
                      }
                    ]
                  }
                }""",
        )
        with self.assertRaisesRegex(
            disk_layout.InvalidLayoutError, 'Layout "base" missing "label"'
        ):
            disk_layout.DiskLayout(self.layout_json)

        # unknown entry.
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "fs_block_size": 4096
                  },
                  "layouts": {
                    "base": [
                      {
                        "num": 1,
                        "type": "data",
                        "label": "rootfs",
                        "unknown": 1
                      }
                    ]
                  }
                }""",
        )
        with self.assertRaisesRegex(
            disk_layout.InvalidLayoutError,
            "Unknown items in layout base: " "{'unknown'}",
        ):
            disk_layout.DiskLayout(self.layout_json)

    def testJSONFileSystemFields(self):
        """Test filesystem fields."""
        # fs_size > fs_size_min size.
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "fs_block_size": 4096
                  },
                  "layouts": {
                    "base": [
                      {
                        "num": 1,
                        "type": "data",
                        "label": "rootfs",
                        "size": "24 MB",
                        "fs_size": "3MB",
                        "fs_align": "2MB"
                      }
                    ]
                  }
                }""",
        )
        with self.assertRaisesRegex(
            disk_layout.InvalidSizeError,
            ".*is not an even multiple of fs_align.*",
        ):
            disk_layout.DiskLayout(self.layout_json)

        # test fs_align in metadata
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "fs_block_size": 4096
                  },
                  "layouts": {
                    "base": []
                  }
                }""",
        )
        layout = disk_layout.DiskLayout(self.layout_json)
        # pylint: disable-msg=W0212
        self.assertEqual(
            layout._disk_layout_config["metadata"]["fs_align"], 4096
        )

        # test invalid fs_align in metadata
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "fs_block_size": 400,
                    "fs_align": 300
                  },
                  "layouts": {
                    "base": []
                  }
                }""",
        )
        with self.assertRaisesRegex(
            disk_layout.InvalidLayoutError, "fs_align.*"
        ):
            disk_layout.DiskLayout(self.layout_json)

    def testPartitionOrderPreservedWithBase(self):
        """Test the order of the partitions is the same as in the parent."""
        osutils.WriteFile(
            self.parent_layout_json,
            """{
                  "metadata": {
                    "fs_block_size": 4096
                  },
                  "layouts": {
                    "common": [
                      {
                        "num": 3,
                        "label": "Part 3",
                        "type": "data"
                      },
                      {
                        "num": 2,
                        "label": "Part 2",
                        "type": "data"
                      },
                      {
                        "num": 1,
                        "label": "Part 1",
                        "type": "data"
                      }
                    ],
                    "base": []
                  }
                }""",
        )
        parent_layout = disk_layout.DiskLayout(self.parent_layout_json)

        # Test also that even overriding one partition keeps all of them in
        # order.
        osutils.WriteFile(
            self.layout_json,
            """{
                  "parent": "%s",
                  "layouts": {
                    "common": [
                      {
                        "num": 2,
                        "label": "Part 2"
                      }
                    ],
                    "base": [
                      {
                        "num": 1,
                        "label": "Part 1"
                      }
                    ]
                  }
                }"""
            % self.parent_layout_json,
        )
        layout = disk_layout.DiskLayout(self.layout_json)
        # pylint: disable-msg=W0212
        self.assertEqual(
            parent_layout._disk_layout_config, layout._disk_layout_config
        )

    def testGetTableTotalsSizeIsAccurate(self):
        """Test primary_entry_array_lba results in an accurate block count."""
        test_params = (
            # block_size, primary_entry_array_padding_bytes (in blocks),
            # partition size (MiB)
            (512, 2, 32),
            (1024, 2, 32),
            (512, 2, 64),
            (512, 32768, 32),
            (1024, 32768, 32),
            (1024, 32768, 64),
        )
        for i in test_params:
            osutils.WriteFile(
                self.layout_json,
                """{
                      "metadata": {
                        "block_size": %d,
                        "fs_block_size": 4096,
                        "primary_entry_array_padding_bytes": %d
                      },
                      "layouts": {
                        "base": [
                          {
                            "num": 1,
                            "label": "data",
                            "type": "blank",
                            "size": "%d MiB"
                          }
                        ]
                      }
                    }"""
                % (i[0], i[1] * i[0], i[2]),
            )

            layout = disk_layout.DiskLayout(self.layout_json)
            # pylint: disable-msg=W0212
            partitions = layout._image_partitions["base"]
            totals = layout.GetTableTotals(partitions)
            self.assertEqual(
                totals["byte_count"],
                disk_layout.START_SECTOR
                + i[1] * i[0]
                + sum([x["bytes"] for x in partitions])
                + disk_layout.SECONDARY_GPT_BYTES,
            )

    def testMultipleParents(self):
        """Test that multiple inheritance works."""
        osutils.WriteFile(
            self.parent_layout_json,
            """{
                  "metadata": {
                    "fs_block_size": 1000
                  },
                  "layouts": {
                    "common": [
                      {
                        "num": 1,
                        "label": "Part 1",
                        "type": "rootfs"
                      }
                    ],
                    "base": [
                      {
                        "num": 2,
                        "label": "Part 2",
                        "type": "data",
                        "fs_size_min": 1000
                      },
                      {
                        "num": 12,
                        "label": "Part 12",
                        "type": "kernel",
                        "size": 2000,
                        "fs_size": 1000
                      }
                    ]
                  }
                }""",
        )
        osutils.WriteFile(
            self.another_parent_layout_json,
            """{
                  "layouts": {
                    "common": [
                      {
                        "num": 1,
                        "label": "Part 1",
                        "type": "rootfs",
                        "size": 3000,
                        "fs_size_min": 2000
                      }
                    ],
                    "base": [
                      {
                        "num": 2,
                        "label": "new Part 2",
                        "type": "data",
                        "fs_size_min": 2000
                      }
                    ]
                  }
                }""",
        )
        osutils.WriteFile(
            self.layout_json,
            """{
                  "parent": "%s %s",
                  "layouts": {
                    "common": [
                      {
                        "num": 1,
                        "label": "new Part 1",
                        "size": 2000
                      }
                    ]
                  }
                }"""
            % (self.parent_layout_json, self.another_parent_layout_json),
        )

        layout = disk_layout.DiskLayout(self.layout_json)
        # pylint: disable-msg=W0212
        self.assertDictEqual(
            layout._disk_layout_config,
            {
                "layouts": {
                    "common": [
                        {
                            "num": 1,
                            "label": "new Part 1",
                            "type": "rootfs",
                            "fs_size_min": 2000,
                            "bytes": 2000,
                            "size": 2000,
                            "features": [],
                        }
                    ],
                    "base": [
                        {
                            "num": 2,
                            "label": "new Part 2",
                            "type": "data",
                            "fs_size_min": 2000,
                            "bytes": 1,
                            "features": [],
                        },
                        {
                            "num": 12,
                            "label": "Part 12",
                            "type": "kernel",
                            "size": 2000,
                            "fs_size": 1000,
                            "fs_bytes": 1000,
                            "bytes": 2000,
                            "features": [],
                        },
                        {
                            "num": 1,
                            "label": "new Part 1",
                            "type": "rootfs",
                            "fs_size_min": 2000,
                            "bytes": 2000,
                            "size": 2000,
                            "features": [],
                        },
                    ],
                },
                "metadata": {"fs_block_size": 1000, "fs_align": 1000},
            },
        )

    def testGapPartitionsAreIncluded(self):
        """Test empty partitions (gaps) can be included in the child layout."""
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "fs_block_size": 1000
                  },
                  "layouts": {
                    "base": [
                      {
                        "num": 2,
                        "label": "Part 2",
                        "type": "rootfs"
                      },
                      {
                        # Pad out, but not sure why.
                        "type": "blank",
                        "size": "64 MiB"
                      },
                      {
                        "num": 1,
                        "label": "Part 1",
                        "type": "data"
                      }
                    ]
                  }
                }""",
        )
        layout = disk_layout.DiskLayout(self.layout_json)
        # pylint: disable-msg=W0212
        self.assertDictEqual(
            layout._disk_layout_config,
            {
                "metadata": {"fs_block_size": 1000, "fs_align": 1000},
                "layouts": {
                    "base": [
                        {
                            "num": 2,
                            "label": "Part 2",
                            "type": "rootfs",
                            "bytes": 1,
                            "features": [],
                        },
                        {
                            "type": "blank",
                            "size": "64 MiB",
                            "bytes": 67108864,
                            "features": [],
                        },
                        {
                            "num": 1,
                            "label": "Part 1",
                            "type": "data",
                            "bytes": 1,
                            "features": [],
                        },
                    ],
                    "common": [],
                },
            },
        )

    def testPartitionOrderShouldMatch(self):
        """Test the partition order in parent and child layouts must match."""
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "fs_block_size": 1000
                  },
                  "layouts": {
                    "common": [
                      {"num": 1, "type": "rootfs", "label": "Part1"},
                      {"num": 2, "type": "data", "label": "Part2"}
                    ],
                    "base": [
                      {"num": 2, "type": "data", "label": "Part2"},
                      {"num": 1, "type": "rootfs", "label": "Part1"}
                    ]
                  }
                }""",
        )
        with self.assertRaises(disk_layout.ConflictingPartitionOrderError):
            disk_layout.DiskLayout(self.layout_json)

    def testOnlySharedPartitionsOrderMatters(self):
        """Test that only the order of the partition in both layouts matters."""
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "fs_block_size": 1000
                  },
                  "layouts": {
                    "common": [
                      {"num": 1, "type": "rootfs", "label": "Part1"},
                      {"num": 2, "type": "data", "label": "Part2"},
                      {"num": 3, "type": "firmware", "label": "Part3"}
                    ],
                    "base": [
                      {"num": 2, "type": "data", "label": "Part2"},
                      {"num": 5, "type": "bootloader", "label": "Part5"},
                      {"num": 3, "type": "firmware", "label": "Part3"},
                      {"num": 12, "type": "kernel", "label": "Part12"}
                    ]
                  }
                }""",
        )
        layout = disk_layout.DiskLayout(self.layout_json)
        # pylint: disable-msg=W0212
        self.assertDictEqual(
            layout._disk_layout_config,
            {
                "metadata": {"fs_block_size": 1000, "fs_align": 1000},
                "layouts": {
                    "common": [
                        {
                            "num": 1,
                            "type": "rootfs",
                            "label": "Part1",
                            "bytes": 1,
                            "features": [],
                        },
                        {
                            "num": 2,
                            "type": "data",
                            "label": "Part2",
                            "bytes": 1,
                            "features": [],
                        },
                        {
                            "num": 3,
                            "type": "firmware",
                            "label": "Part3",
                            "bytes": 1,
                            "features": [],
                        },
                    ],
                    "base": [
                        {
                            "num": 1,
                            "type": "rootfs",
                            "label": "Part1",
                            "bytes": 1,
                            "features": [],
                        },
                        {
                            "num": 2,
                            "type": "data",
                            "label": "Part2",
                            "bytes": 1,
                            "features": [],
                        },
                        {
                            "num": 5,
                            "type": "bootloader",
                            "label": "Part5",
                            "bytes": 1,
                            "features": [],
                        },
                        {
                            "num": 3,
                            "type": "firmware",
                            "label": "Part3",
                            "bytes": 1,
                            "features": [],
                        },
                        {
                            "num": 12,
                            "type": "kernel",
                            "label": "Part12",
                            "bytes": 1,
                            "features": [],
                        },
                    ],
                },
            },
        )

    def testFileSystemSizeMustBePositive(self):
        """Test that zero or negative file system size will raise exception."""
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "block_size": "512",
                    "fs_block_size": "4 KiB"
                  },
                  "layouts": {
                    "base": [
                      {
                        "num": 1,
                        "type": "rootfs",
                        "label": "ROOT-A",
                        "fs_size": "0 KiB"
                      }
                    ]
                  }
                }""",
        )
        with self.assertRaisesRegex(
            disk_layout.InvalidSizeError, ".*must be positive"
        ):
            disk_layout.DiskLayout(self.layout_json)

    def testFileSystemSizeLargerThanPartition(self):
        """Test that file system size must not be greater than partition."""
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "block_size": "512",
                    "fs_block_size": "4 KiB"
                  },
                  "layouts": {
                    "base": [
                      {
                        "num": 1,
                        "type": "rootfs",
                        "label": "ROOT-A",
                        "size": "4 KiB",
                        "fs_size": "8 KiB"
                      }
                    ]
                  }
                }""",
        )
        with self.assertRaisesRegex(
            disk_layout.InvalidSizeError, ".*may not be larger than partition.*"
        ):
            disk_layout.DiskLayout(self.layout_json)

    def testFileSystemSizeNotMultipleBlocks(self):
        """Test file system size must be multiples of file system blocks."""
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "block_size": "512",
                    "fs_block_size": "4 KiB"
                  },
                  "layouts": {
                    "base": [
                      {
                        "num": 1,
                        "type": "rootfs",
                        "label": "ROOT-A",
                        "size": "4 KiB",
                        "fs_size": "3 KiB"
                      }
                    ]
                  }
                }""",
        )
        with self.assertRaisesRegex(
            disk_layout.InvalidSizeError, ".*not an even multiple of fs_align.*"
        ):
            disk_layout.DiskLayout(self.layout_json)

    def testFileSystemSizeForUbiWithNoPageSize(self):
        """Test that "page_size" must be present to calculate UBI fs size."""
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "block_size": "512",
                    "fs_block_size": "4 KiB"
                  },
                  "layouts": {
                    "base": [
                      {
                        "num": 1,
                        "type": "rootfs",
                        "format": "ubi",
                        "label": "ROOT-A",
                        "size": "4 KiB",
                        "fs_size": "4 KiB"
                      }
                    ]
                  }
                }""",
        )
        with self.assertRaisesRegex(
            disk_layout.InvalidLayoutError, ".*page_size.*"
        ):
            disk_layout.DiskLayout(self.layout_json)

    def testFileSystemSizeForUbiWithNoEraseBlockSize(self):
        """Test "erase_block_size" must be present to calculate UBI fs size."""
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "block_size": "512",
                    "fs_block_size": "4 KiB"
                  },
                  "layouts": {
                    "base": [
                      {
                        "num": "metadata",
                        "page_size": "4 KiB"
                      },
                      {
                        "num": 1,
                        "type": "rootfs",
                        "format": "ubi",
                        "label": "ROOT-A",
                        "size": "4 KiB",
                        "fs_size": "4 KiB"
                      }
                    ]
                  }
                }""",
        )
        with self.assertRaisesRegex(
            disk_layout.InvalidLayoutError, ".*erase_block_size.*"
        ):
            disk_layout.DiskLayout(self.layout_json)

    def testFileSystemSizeForUbiIsNotMultipleOfUbiEraseBlockSize(self):
        """Test that we raise when fs_size is not multiple of eraseblocks."""
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "block_size": "512",
                    "fs_block_size": "4 KiB"
                  },
                  "layouts": {
                    "base": [
                      {
                        "num": "metadata",
                        "page_size": "4 KiB",
                        "erase_block_size": "262144"
                      },
                      {
                        "num": 1,
                        "type": "rootfs",
                        "format": "ubi",
                        "label": "ROOT-A",
                        "size": "256 KiB",
                        "fs_size": "256 KiB"
                      }
                    ]
                  }
                }""",
        )
        with self.assertRaisesRegex(
            disk_layout.InvalidSizeError,
            '.*to "248 KiB" in the "common" layout.*',
        ):
            disk_layout.DiskLayout(self.layout_json)

    def testFileSystemSizeForUbiIsMultipleOfUbiEraseBlockSize(self):
        """Test everything is okay when fs_size is multiple of eraseblocks."""
        osutils.WriteFile(
            self.layout_json,
            """{
                  "metadata": {
                    "block_size": "512",
                    "fs_block_size": "4 KiB"
                  },
                  "layouts": {
                    "base": [
                      {
                        "num": "metadata",
                        "page_size": "4 KiB",
                        "erase_block_size": "262144"
                      },
                      {
                        "num": 1,
                        "type": "rootfs",
                        "format": "ubi",
                        "label": "ROOT-A",
                        "size": "256 KiB",
                        "fs_size": "253952"
                      }
                    ]
                  }
                }""",
        )
        layout = disk_layout.DiskLayout(self.layout_json)
        # pylint: disable-msg=W0212
        self.assertEqual(
            layout._disk_layout_config,
            {
                "layouts": {
                    "base": [
                        {
                            "erase_block_size": 262144,
                            "features": [],
                            "num": "metadata",
                            "page_size": 4096,
                            "type": "blank",
                        },
                        {
                            "bytes": 262144,
                            "features": [],
                            "format": "ubi",
                            "fs_bytes": 253952,
                            "fs_size": "253952",
                            "label": "ROOT-A",
                            "num": 1,
                            "size": "256 KiB",
                            "type": "rootfs",
                        },
                    ],
                    "common": [],
                },
                "metadata": {
                    "block_size": "512",
                    "fs_align": 4096,
                    "fs_block_size": 4096,
                },
            },
        )


class UtilityTest(cros_test_lib.MockTestCase):
    """Test various utility functions in disk_layout.py."""

    def testParseHumanNumber(self):
        """Test that ParseHumanNumber is correct."""
        test_cases = [
            ("1", 1),
            ("2", 2),
            ("1KB", 1000),
            ("1KiB", 1024),
            ("1 K", 1024),
            ("1 KiB", 1024),
            ("3 MB", 3000000),
            ("4 MiB", 4 * 2**20),
            ("5GB", 5 * 10**9),
            ("6GiB", 6 * 2**30),
            ("7TB", 7 * 10**12),
            ("8TiB", 8 * 2**40),
            ("-4", -4),
            ("-5GB", -5 * 10**9),
            ("-6GiB", -6 * 2**30),
            ("-7TB", -7 * 10**12),
            ("-8TiB", -8 * 2**40),
        ]
        for inp, exp in test_cases:
            self.assertEqual(disk_layout.ParseHumanNumber(inp), exp)

    def testParseHumanNumberInvalid(self):
        """Test that ParseHumanNumber raises exception for invalid input."""
        test_cases = ["10uB", "30 BT", "40 Tg", "TiB", "-GB"]

        for inp in test_cases:
            with self.assertRaises(disk_layout.InvalidAdjustmentError):
                disk_layout.ParseHumanNumber(inp)

    def testProduceHumanNumber(self):
        """Test that ProduceHumanNumber is correct."""
        test_cases = [
            ("1", 1),
            ("2", 2),
            ("1 KB", 1000),
            ("1 KiB", 1024),
            ("3 MB", 3 * 10**6),
            ("4 MiB", 4 * 2**20),
            ("5 GB", 5 * 10**9),
            ("6 GiB", 6 * 2**30),
            ("7 TB", 7 * 10**12),
            ("8 TiB", 8 * 2**40),
        ]
        for exp, inp in test_cases:
            self.assertEqual(disk_layout.ProduceHumanNumber(inp), exp)

    def testGetScriptShell(self):
        """Verify GetScriptShell works."""
        data = disk_layout.GetScriptShell()
        self.assertIn("#!/bin/sh", data)
        self.assertIn(
            str(constants.CHROMITE_DIR / "sdk" / "cgpt_shell.sh"), data
        )

    def testParseProduce(self):
        """Test ParseHumanNumber(ProduceHumanNumber()) yields same value."""
        test_cases = [
            1,
            2,
            -2,
            1000,
            1024,
            2 * 10**6,
            2 * 2**20,
            3 * 10**9,
            3 * 2**30,
            4 * 10**12,
            4 * 2**40,
            -4 * 2**40,
        ]
        for n in test_cases:
            self.assertEqual(
                disk_layout.ParseHumanNumber(disk_layout.ProduceHumanNumber(n)),
                n,
            )

    def testParseRelativeNumber(self):
        """Verify ParseRelativeNumber()."""
        test_cases = [
            ((1000, "90%"), 900),
            ((1000, "-10"), 990),
            ((1000, "80"), 80),
            ((1000, "8 TiB"), 8 * 2**40),
        ]
        for inp, output in test_cases:
            self.assertEqual(
                disk_layout.ParseRelativeNumber(inp[0], inp[1]), output
            )
