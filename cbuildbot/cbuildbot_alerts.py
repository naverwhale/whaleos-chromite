# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for printing specially formatted events for cbuildbot reporting."""

import sys

# Import as private to avoid polluting module namespace.
from chromite.lib import buildbot_annotations as _annotations

# Only buildbot aware entry-points need to spew buildbot specific logs. Require
# user action for the special log lines.
_buildbot_markers_enabled = False


def EnableBuildbotMarkers():
  # pylint: disable=global-statement
  global _buildbot_markers_enabled
  _buildbot_markers_enabled = True


def _PrintForBuildbot(handle, annotation_class, *args):
  """Log a line for buildbot.

  This function dumps a line to log recognizable by buildbot if
  EnableBuildbotMarkers has been called. Otherwise, it dumps the same line in a
  human friendly way that buildbot ignores.

  Args:
    handle: The pipe to dump the log to. If None, log to sys.stderr.
    annotation_class: Annotation subclass for the type of buildbot log.
    buildbot_tag: A tag specifying the type of buildbot log.
    *args: The rest of the str arguments to be dumped to the log.
  """
  if handle is None:
    handle = sys.stderr
  if annotation_class == _annotations.SetEmailNotifyProperty:
    annotation = annotation_class(*args)
  else:
    # Cast each argument, because we end up getting all sorts of objects from
    # callers.
    str_args = [str(x) for x in args]
    annotation = annotation_class(*str_args)
  if _buildbot_markers_enabled:
    line = str(annotation)
  else:
    line = annotation.human_friendly
  handle.write('\n' + line + '\n')


def PrintBuildbotLink(text, url, handle=None):
  """Prints out a link to buildbot."""
  _PrintForBuildbot(handle, _annotations.StepLink, text, url)


def PrintKitchenSetBuildProperty(name, data, handle=None):
  """Prints out a request to set a build property to a JSON value."""
  _PrintForBuildbot(handle, _annotations.SetBuildProperty, name, data)


def PrintKitchenSetEmailNotifyProperty(name, data, handle=None):
  """Prints out a request to set an email_notify build property."""
  _PrintForBuildbot(handle, _annotations.SetEmailNotifyProperty, name, data)


def PrintBuildbotStepText(text, handle=None):
  """Prints out stage text to buildbot."""
  _PrintForBuildbot(handle, _annotations.StepText, text)


def PrintBuildbotStepWarnings(handle=None):
  """Marks a stage as having warnings."""
  PrintBuildbotStepText('[FAILED BUT FORGIVEN]', handle=handle)
  # Warnings not supported by LUCI, so working around until re-added.
  _PrintForBuildbot(handle, _annotations.StepWarnings)


def PrintBuildbotStepFailure(handle=None):
  """Marks a stage as having failures."""
  _PrintForBuildbot(handle, _annotations.StepFailure)


def PrintBuildbotStepName(name, handle=None):
  """Marks a step name for buildbot to display."""
  _PrintForBuildbot(handle, _annotations.BuildStep, name)
