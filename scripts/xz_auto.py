# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Run xz from PATH with a thread for each core in the system."""

from __future__ import division

import multiprocessing
import os

from chromite.lib import commandline
from chromite.lib import osutils
from chromite.utils import memoize


@memoize.Memoize
def HasPixz():
  """Returns path to pixz if it's on PATH or None otherwise."""
  return osutils.Which('pixz')


@memoize.Memoize
def GetJobCount():
  """Returns half of the total number of the machine's CPUs as a string.

  Returns half rather than all of them to avoid starving out other parallel
  processes on the same machine.
  """
  return str(int(max(1, multiprocessing.cpu_count() / 2)))


def GetDecompressCommand(stdout):
  """Returns decompression command."""
  if HasPixz():
    cmd = ['pixz', '-d', '-p', GetJobCount()]
    if stdout:
      # Explicitly tell pixz the file is the input, so it will dump the output
      # to stdout, instead of automatically choosing an output name.
      cmd.append('-i')
    return cmd
  if stdout:
    return ['xz', '-dc']
  return ['xz', '-d']


def GetParser():
  """Return a command line parser."""
  parser = commandline.ArgumentParser(description=__doc__)
  parser.add_argument(
      '-d',
      '--decompress',
      '--uncompress',
      help='Decompress rather than compress.',
      action='store_true')
  parser.add_argument(
      '-c',
      dest='stdout',
      action='store_true',
      help="Write to standard output and don't delete input files.")
  return parser


def main(argv):
  parser = GetParser()
  known_args, argv = parser.parse_known_args()
  if '-i' in argv or '-o' in argv:
    parser.error('It is invalid to use -i or -o with xz_auto')

  # xz doesn't support multi-threaded decompression, so try using pixz for that.
  if known_args.decompress:
    args = GetDecompressCommand(known_args.stdout)
    os.execvp(args[0], args + argv)
  else:
    cmd = ['xz', '-T0']
    if known_args.stdout:
      cmd.append('-c')
    os.execvp(cmd[0], cmd + argv)
