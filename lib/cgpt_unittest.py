# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test chromite.lib.cgpt"""

from chromite.lib import cgpt
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import path_util


CGPT_SHOW_OUTPUT = """start        size    part  contents
           0           1          PMBR (Boot GUID: E32D9819-048F-8E41-B743-2A8102897F1B)
           1           1          Pri GPT header
           2          32          Pri GPT table
     5455872     8401017       1  Label: "STATE"
                                  Type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
                                  UUID: 31CD4A3B-C504-354B-AC37-0852D2E0A44C
                                  Attr: [0]
      405504       65536       2  Label: "KERN-A"
                                  Type: FE3A2A5D-4F32-41A7-B725-ACCC3285A309
                                  UUID: 1F94CE4D-7EF3-AE4C-A0F3-03FBB81699B8
                                  Attr: [1ff]
      471040     4915200       3  Label: "ROOT-A"
                                  Type: 3CB8E202-3B7E-47DD-8A3C-7FF2A13CFCEC
                                  UUID: FC606456-D6E0-C64D-A82E-BA7B027D2B20
                                  Attr: [0]
     5386240       65536       4  Label: "KERN-B"
                                  Type: FE3A2A5D-4F32-41A7-B725-ACCC3285A309
                                  UUID: 2B2D493A-22B8-0742-A56A-D31944B15271
                                  Attr: [0]
     5451776        4096       5  Label: "ROOT-B"
                                  Type: 3CB8E202-3B7E-47DD-8A3C-7FF2A13CFCEC
                                  UUID: D3B939D0-01DB-C84E-8E3B-7DCF861F2321
                                  Attr: [0]
      262208           1       6  Label: "KERN-C"
                                  Type: FE3A2A5D-4F32-41A7-B725-ACCC3285A309
                                  UUID: AA93D568-6AF0-0B4E-88E8-FBF3B0E54F0F
                                  Attr: [0]
      262209           1       7  Label: "ROOT-C"
                                  Type: 3CB8E202-3B7E-47DD-8A3C-7FF2A13CFCEC
                                  UUID: A5DFEF3B-58F0-0F48-B326-5BF6DAE2E503
                                  Attr: [0]
      266240        8192       8  Label: "OEM"
                                  Type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
                                  UUID: 18A64E9D-FF35-A248-B6D4-AE943A93386D
                                  Attr: [0]
          64      262144       9  Label: "MINIOS-A"
                                  Type: 09845860-705F-4BB5-B16C-8A8A099CAF52
                                  UUID: 0A379155-6C27-1A45-AC83-EF96F0588734
                                  Attr: [0]
    13856889        4096      10  Label: "reserved"
                                  Type: 2E0A753D-9E48-43B0-8337-B15192CB1B5E
                                  UUID: F31ACAD0-CDA0-4041-91FD-663C0F9693CF
                                  Attr: [0]
    13856889        4096      11  Label: "reserved"
                                  Type: 2E0A753D-9E48-43B0-8337-B15192CB1B5E
                                  UUID: 2697A3F2-37A1-1348-8A90-52B83C812B69
                                  Attr: [0]
      274432      131072      12  Label: "EFI-SYSTEM"
                                  Type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
                                  UUID: E32D9819-048F-8E41-B743-2A8102897F1B
                                  Attr: [0]
    13861000          32          Sec GPT table
    13861032           1          Sec GPT header"""


class TestDisk(cros_test_lib.RunCommandTestCase):
  """Test Disk class."""

  def getMockDisk(self):
    """Returns new Disk based on CGPT_SHOW_OUTPUT."""
    self.rc.SetDefaultCmdResult(output=CGPT_SHOW_OUTPUT)
    return cgpt.Disk.FromImage('foo')

  def testDiskFromImageEmpty(self):
    """Test ReadGpt when cgpt doesn't return an expected list."""
    with self.assertRaises(cgpt.Error):
      cgpt.Disk.FromImage('foo')

  def testDiskFromImage(self):
    """Test ReadGpt with mock cgpt output."""
    which_mock = self.PatchObject(osutils, 'Which', return_value='/path/foo')
    disk = self.getMockDisk()

    which_mock.assert_called_once()
    self.assertCommandCalled(['cgpt', 'show', '-n', 'foo'],
                             enter_chroot=False, capture_output=True,
                             encoding='utf-8')

    self.assertEqual(len(disk.partitions), 12)

    self.assertEqual(disk.partitions[3],
                     cgpt.Partition(part_num=3,
                                    label='ROOT-A',
                                    start=471040,
                                    size=4915200,
                                    part_type='3CB8E202-3B7E-47DD-'
                                              '8A3C-7FF2A13CFCEC',
                                    uuid='FC606456-D6E0-C64D-A82E-BA7B027D2B20',
                                    attr='[0]'))

  def testDiskFromImageCgptMissing(self):
    """Test ReadGpt with mock cgpt output when cpgt is missing."""
    which_mock = self.PatchObject(osutils, 'Which', return_value=None)
    to_chroot_path_mock = self.PatchObject(path_util, 'ToChrootPath',
                                           return_value='foo')
    disk = self.getMockDisk()

    which_mock.assert_called_once()
    to_chroot_path_mock.assert_called_once()

    self.assertCommandCalled(['cgpt', 'show', '-n', 'foo'], enter_chroot=True,
                             capture_output=True, encoding='utf-8')

    self.assertEqual(len(disk.partitions), 12)

    self.assertEqual(disk.partitions[3],
                     cgpt.Partition(part_num=3,
                                    label='ROOT-A',
                                    start=471040,
                                    size=4915200,
                                    part_type='3CB8E202-3B7E-47DD-'
                                              '8A3C-7FF2A13CFCEC',
                                    uuid='FC606456-D6E0-C64D-A82E-BA7B027D2B20',
                                    attr='[0]'))

  def testGetPartitionByLabel(self):
    """Test that mocked disk has all expected partitions."""
    disk = self.getMockDisk()

    for label, part_num in (('STATE', 1),
                            ('KERN-A', 2),
                            ('ROOT-A', 3),
                            ('KERN-B', 4),
                            ('ROOT-B', 5),
                            ('KERN-C', 6),
                            ('ROOT-C', 7),
                            ('OEM', 8),
                            ('MINIOS-A', 9),
                            ('EFI-SYSTEM', 12)):
      self.assertEqual(disk.GetPartitionByLabel(label).part_num, part_num)

  def testGetPartitionByLabelMulitpleLabels(self):
    """Test MultiplePartitionLabel is raised on duplicate label 'reserved'."""
    disk = self.getMockDisk()

    with self.assertRaises(cgpt.MultiplePartitionLabel):
      disk.GetPartitionByLabel('reserved')

  def testGetPartitionByLabelMissingKey(self):
    """Test KeyError is raised on a non-existent label."""
    disk = self.getMockDisk()

    with self.assertRaises(KeyError):
      disk.GetPartitionByLabel('bar')

  def testGetPartitionsByTypeGuid(self):
    """Test that mocked disk has all expected partitions."""
    disk = self.getMockDisk()

    self.assertEqual([p.part_num for p in disk.GetPartitionByTypeGuid(
        '09845860-705F-4BB5-B16C-8A8A099CAF52')], [9])

  def testGetPartitionsByTypeGuidMulti(self):
    """Test that mocked disk has all expected partitions."""
    disk = self.getMockDisk()

    self.assertEqual([p.part_num for p in disk.GetPartitionByTypeGuid(
        '2E0A753D-9E48-43B0-8337-B15192CB1B5E')], [10, 11])
