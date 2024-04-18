# Copyright 2015 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module containing builders intended for testing cbuildbot behaviors."""

import logging

from chromite.cbuildbot.builders import generic_builders
from chromite.cbuildbot.stages import generic_stages


class SuccessStage(generic_stages.BuilderStage):
    """Build stage declares success!"""

    def PerformStage(self):
        logging.info("!!!SuccessStage, FTW!!!")


class FailStage(generic_stages.BuilderStage):
    """Build stage always fails."""

    def PerformStage(self):
        raise Exception("!!!Oh, no! A Fail Stage!!!")


class SucessBuilder(generic_builders.ManifestVersionedBuilder):
    """Very minimal builder that always passes."""

    def RunStages(self):
        """Run a success stage!"""
        self._RunStage(SuccessStage)


class FailBuilder(generic_builders.ManifestVersionedBuilder):
    """Very minimal builder that always fails."""

    def RunStages(self):
        """Run fail stage!"""
        self._RunStage(FailStage)
