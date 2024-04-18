# Copyright 2012 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unittests for config."""

import copy
from unittest import mock

from chromite.cbuildbot import builders
from chromite.cbuildbot.builders import generic_builders
from chromite.config import chromeos_config
from chromite.format import formatters
from chromite.lib import config_lib
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import git
from chromite.lib import osutils


# pylint: disable=protected-access


class ChromeosConfigTestBase(cros_test_lib.TestCase):
    """Base class for tests of chromeos_config.."""

    def setUp(self):
        self.site_config = chromeos_config.GetConfig()

    def isReleaseBranch(self):
        ge_build_config = config_lib.LoadGEBuildConfigFromFile()
        return ge_build_config["release_branch"]


class ConfigDumpTest(ChromeosConfigTestBase):
    """Tests related to config_dump.json & chromeos_config.py"""

    def testDump(self):
        """Ensure generated files are up to date."""
        # config_dump.json
        new_dump = self.site_config.SaveConfigToString()
        old_dump = osutils.ReadFile(constants.CHROMEOS_CONFIG_FILE)

        if new_dump != old_dump:
            self.fail(
                "config_dump.json does not match the defined configs. Run "
                "config/refresh_generated_files"
            )

        # watefall_layout_dump.txt
        # We run this as a sep program to avoid the config cache.
        cmd = constants.CHROMITE_BIN_DIR / "cros_show_waterfall_layout"
        result = cros_build_lib.run(
            [cmd], capture_output=True, encoding="utf-8"
        )

        # Capturing cros_show_waterfall_layout gives 2 newlines at the end, but
        # cros format wants 1, which refresh_generated_files uses to prevent
        # presubmit hook errors, so format the data.
        new_dump_raw = result.stdout
        new_dump = formatters.whitespace.Data(new_dump_raw)
        # Quick verification of above comment.
        self.assertEqual(new_dump_raw.strip(), new_dump.strip())
        old_dump = osutils.ReadFile(constants.WATERFALL_CONFIG_FILE)

        if new_dump != old_dump:
            self.fail(
                "waterfall_layout_dump.txt does not match the defined configs. "
                "Run config/refresh_generated_files"
            )

        # luci-scheduler.cfg
        # We run this as a sep program to avoid the config cache.
        cmd = constants.CHROMITE_DIR / "scripts" / "gen_luci_scheduler"
        result = cros_build_lib.run(
            [cmd], capture_output=True, encoding="utf-8"
        )

        new_dump = result.stdout
        old_dump = osutils.ReadFile(constants.LUCI_SCHEDULER_CONFIG_FILE)

        if new_dump != old_dump:
            self.fail(
                "luci-scheduler.cfg does not match the defined configs. Run "
                "config/refresh_generated_files"
            )

    def testSaveLoadReload(self):
        """Make sure that loading and reloading the config is a no-op."""
        site_config_str = self.site_config.SaveConfigToString()
        loaded = config_lib.LoadConfigFromString(site_config_str)

        self.longMessage = True
        for name in self.site_config:
            self.assertDictEqual(loaded[name], self.site_config[name], name)

        # This includes templates and the default build config.
        self.assertEqual(self.site_config, loaded)

        loaded_str = loaded.SaveConfigToString()

        self.assertEqual(site_config_str, loaded_str)

        # Cycle through save load again, just for completeness.
        loaded2 = config_lib.LoadConfigFromString(loaded_str)
        loaded2_str = loaded2.SaveConfigToString()
        self.assertEqual(loaded_str, loaded2_str)

    def testFullDump(self):
        """Make sure we can dump long content without crashing."""
        # Note: This test takes ~ 1 second to run.
        self.site_config.DumpExpandedConfigToString()


class FindConfigsForBoardTest(cros_test_lib.TestCase):
    """Test locating of official build for a board.

    This test class used to live in config_lib_unittest, but was moved
    here to help make lib/ hermetic and not depend on chromite/cbuildbot.
    """

    def setUp(self):
        self.config = chromeos_config.GetConfig()

    def _CheckFullConfig(
        self, board, external_expected=None, internal_expected=None
    ):
        """Check FindFullConfigsForBoard has expected results.

        Args:
            board: Argument to pass to FindFullConfigsForBoard.
            external_expected: Expected config name (singular) to be found.
            internal_expected: Expected config name (singular) to be found.
        """

        def check_expected(l, expected):
            if expected is not None:
                self.assertTrue(expected in [v["name"] for v in l])

        external, internal = self.config.FindFullConfigsForBoard(board)
        self.assertFalse(
            external_expected is None and internal_expected is None
        )
        check_expected(external, external_expected)
        check_expected(internal, internal_expected)

    def _CheckCanonicalConfig(self, board, ending):
        self.assertEqual(
            "-".join((board, ending)),
            self.config.FindCanonicalConfigForBoard(board)["name"],
        )

    def testExternal(self):
        """Test finding of a full builder."""
        self._CheckFullConfig(
            "amd64-generic", external_expected="amd64-generic-full"
        )

    def testInternal(self):
        """Test finding of a release builder."""
        self._CheckFullConfig("eve", internal_expected="eve-release")

    def testExternalCanonicalResolution(self):
        """Test an external canonical config."""
        self._CheckCanonicalConfig("amd64-generic", "full")

    def testAFDOCanonicalResolution(self):
        """Test prefer non-AFDO over AFDO builder."""
        self._CheckCanonicalConfig("eve", "release")

    def testOneFullConfigPerBoard(self):
        """There is at most one 'full' config for a board."""

        # Verifies the number of external 'full' and internal 'release' build
        # per board.  This is to ensure that we fail any new configs that
        # wrongly have names like *-bla-release or *-bla-full. This case can
        # also be caught if the new suffix was added to
        # config_lib.CONFIG_TYPE_DUMP_ORDER (see testNonOverlappingConfigTypes),
        # but that's not guaranteed to happen.
        def AtMostNumConfigs(board, label, configs, number):
            if len(configs) > number:
                self.fail(
                    "Found more than one %s config for %s: %r"
                    % (label, board, [c["name"] for c in configs])
                )

        boards = set()
        for build_config in self.config.values():
            boards.update(build_config["boards"])

        # Sanity check of the boards.
        self.assertTrue(boards)

        for b in boards:
            numExternal = 2 if b == "amd64-generic" else 1
            external, internal = self.config.FindFullConfigsForBoard(b)
            AtMostNumConfigs(b, "external", external, numExternal)
            AtMostNumConfigs(b, "internal", internal, 1)


class ConfigClassTest(ChromeosConfigTestBase):
    """Tests of the config class itself."""

    def testAppendUseflags(self):
        base_config = config_lib.BuildConfig(useflags=[])
        inherited_config_1 = base_config.derive(
            useflags=config_lib.append_useflags(["foo", "bar", "-baz"])
        )
        inherited_config_2 = inherited_config_1.derive(
            useflags=config_lib.append_useflags(["-bar", "baz"])
        )
        self.assertEqual(base_config.useflags, [])
        self.assertEqual(inherited_config_1.useflags, ["-baz", "bar", "foo"])
        self.assertEqual(inherited_config_2.useflags, ["-bar", "baz", "foo"])


class CBuildBotTest(ChromeosConfigTestBase):
    """General tests of chromeos_config."""

    def findAllSlaveBuilds(self):
        """Test helper for finding all slave builds.

        Returns:
            Set of slave build config names.
        """
        all_slaves = set()
        for config in self.site_config.values():
            if config.master:
                all_slaves.update(config.slave_configs)

        return all_slaves

    def _GetBoardTypeToBoardsDict(self):
        """Get boards dict.

        Returns:
            A dict mapping a board type to a collections of board names.
        """
        ge_build_config = config_lib.LoadGEBuildConfigFromFile()
        return chromeos_config.GetBoardTypeToBoardsDict(ge_build_config)

    def testConfigsKeysMismatch(self):
        """Verify that all configs contain exactly the default keys.

        This checks for mispelled keys, or keys that are somehow removed.
        """
        expected_keys = set(self.site_config.GetDefault())
        for build_name, config in self.site_config.items():
            config_keys = set(config)

            extra_keys = config_keys.difference(expected_keys)
            self.assertFalse(
                extra_keys,
                (
                    "Config %s has extra values %s"
                    % (build_name, list(extra_keys))
                ),
            )

            missing_keys = expected_keys.difference(config_keys)
            self.assertFalse(
                missing_keys,
                (
                    "Config %s is missing values %s"
                    % (build_name, list(missing_keys))
                ),
            )

    def testConfigsHaveName(self):
        """Configs must have names set."""
        for build_name, config in self.site_config.items():
            self.assertTrue(build_name == config["name"])

    def testConfigsHaveValidDisplayLabel(self):
        """Configs must have names set."""
        for build_name, config in self.site_config.items():
            self.assertIn(
                config.display_label,
                config_lib.ALL_DISPLAY_LABEL,
                'Invalid display_label "%s" on "%s"'
                % (config.display_label, build_name),
            )

    def testConfigsHaveValidLuciBuilder(self):
        """Configs must have names set."""
        for build_name, config in self.site_config.items():
            self.assertIn(
                config.luci_builder,
                config_lib.ALL_LUCI_BUILDER,
                'Invalid luci_builder "%s" on "%s"'
                % (config.luci_builder, build_name),
            )

    def testMasterSlaveConfigsExist(self):
        """Configs listing slave configs, must list valid configs."""
        for config in self.site_config.values():
            if config.master:
                # Any builder with slaves must set both of these.
                self.assertTrue(config.master)
                self.assertIsNotNone(config.slave_configs)

                # If a builder lists slave config names, ensure they are all
                # valid, and have an assigned waterfall.
                for slave_name in config.slave_configs:
                    self.assertIn(slave_name, self.site_config)
            else:
                self.assertIsNone(config.slave_configs)

    def testMasterSlaveConfigsSorted(self):
        """Configs listing slave configs, must list valid configs."""
        for config in self.site_config.values():
            if config.slave_configs is not None:
                expected = sorted(config.slave_configs)

                self.assertEqual(config.slave_configs, expected)

    def testOnlySlaveConfigsNotImportant(self):
        """Configs listing slave configs, must list valid configs."""
        all_slaves = self.findAllSlaveBuilds()

        for config in self.site_config.values():
            self.assertTrue(
                config.important or config.name in all_slaves,
                "%s is not marked important, but is not a slave." % config.name,
            )

    def testConfigUseflags(self):
        """Useflags must be lists.

        Strings are interpreted as arrays of characters for this, which is not
        useful.
        """
        for build_name, config in self.site_config.items():
            useflags = config.get("useflags")
            if not useflags is None:
                self.assertIsInstance(
                    useflags,
                    list,
                    "Config %s: useflags should be a list." % build_name,
                )

    def testBoards(self):
        """Verify 'boards' is explicitly set for every config."""
        for build_name, config in self.site_config.items():
            self.assertIsInstance(
                config["boards"],
                (tuple, list),
                "Config %s doesn't have a list of boards." % build_name,
            )
            self.assertEqual(
                len(set(config["boards"])),
                len(config["boards"]),
                "Config %s has duplicate boards." % build_name,
            )

    def testOverlaySettings(self):
        """Verify overlays and push_overlays have legal values."""
        for build_name, config in self.site_config.items():
            overlays = config["overlays"]
            push_overlays = config["push_overlays"]

            self.assertTrue(
                overlays in [None, "public", "private", "both"],
                "Config %s: has unexpected overlays value." % build_name,
            )
            self.assertTrue(
                push_overlays in [None, "public", "private", "both"],
                "Config %s: has unexpected push_overlays value." % build_name,
            )

            if overlays is None:
                subset = [None]
            elif overlays == "public":
                subset = [None, "public"]
            elif overlays == "private":
                subset = [None, "private"]
            elif overlays == "both":
                subset = [None, "public", "private", "both"]

            self.assertTrue(
                push_overlays in subset,
                (
                    "Config %s: push_overlays should be a subset of overlays."
                    % build_name
                ),
            )

    def testOverlayMaster(self):
        """Verify that only one master is pushing uprevs for each overlay."""
        masters = {}
        for build_name, config in self.site_config.items():
            overlays = config["overlays"]
            push_overlays = config["push_overlays"]
            if (
                overlays
                and push_overlays
                and config["uprev"]
                and config["master"]
                and not config["branch"]
                and not config["workspace_branch"]
                and not config["debug"]
            ):
                other_master = masters.get(push_overlays)
                err_msg = "Found two masters for push_overlays=%s: %s and %s"
                self.assertFalse(
                    other_master,
                    err_msg % (push_overlays, build_name, other_master),
                )
                masters[push_overlays] = build_name

        if "both" in masters:
            self.assertEqual(len(masters), 1, "Found too many masters.")

    def testChromeRev(self):
        """Verify chrome_rev has an expected value"""
        for build_name, config in self.site_config.items():
            self.assertTrue(
                config["chrome_rev"]
                in constants.VALID_CHROME_REVISIONS + [None],
                "Config %s: has unexpected chrome_rev value." % build_name,
            )
            self.assertFalse(
                config["chrome_rev"] == constants.CHROME_REV_LOCAL,
                "Config %s: has unexpected chrome_rev_local value."
                % build_name,
            )
            if config["chrome_rev"]:
                self.assertTrue(
                    config_lib.IsPFQType(config["build_type"]),
                    "Config %s: has chrome_rev but is not a PFQ." % build_name,
                )

    def testBuildType(self):
        """Verifies that all configs use valid build types."""
        for build_name, config in self.site_config.items():
            # For builders that have explicit classes, this check doesn't make
            # sense.
            if config["builder_class_name"]:
                continue
            self.assertIn(
                config["build_type"],
                constants.VALID_BUILD_TYPES,
                "Config %s: has unexpected build_type value." % build_name,
            )

    def testValidUnifiedMasterConfig(self):
        """Make sure any unified master configurations are valid."""
        for build_name, config in self.site_config.items():
            error = "Unified config for %s has invalid values" % build_name
            # Unified masters must be internal and must rev both overlays.
            if config["master"] and config["manifest_version"]:
                self.assertTrue(config["internal"], error)
            elif not config["master"] and config["manifest_version"]:
                # Unified slaves can rev either public or both depending on
                # whether they are internal or not.
                if not config["internal"]:
                    self.assertEqual(
                        config["overlays"], constants.PUBLIC_OVERLAYS, error
                    )

    def testGetSlaves(self):
        """Make sure every master has a valid list of slaves"""
        for build_name, config in self.site_config.items():
            if config.master:
                configs = self.site_config.GetSlavesForMaster(config)
                self.assertEqual(
                    len(configs),
                    len(set(repr(x) for x in configs)),
                    "Duplicate board in slaves of %s will cause upload "
                    "prebuilts failures" % build_name,
                )

    def _getSlaveConfigsForMaster(self, master_config_name):
        """Helper to fetch the configs for all slaves of a given master."""
        master_config = self.site_config[master_config_name]

        # Get a list of all active Paladins.
        return [self.site_config[n] for n in master_config.slave_configs]

    def testGetSlavesOnTrybot(self):
        """Make sure every master has a valid list of slaves"""
        mock_options = mock.Mock()
        mock_options.remote_trybot = True
        for _, config in self.site_config.items():
            if config["master"]:
                configs = self.site_config.GetSlavesForMaster(
                    config, mock_options
                )
                self.assertEqual([], configs)

    def testFactoryFirmwareValidity(self):
        """Ensures that firmware/factory branches have at least 1 valid name."""
        tracking_branch = git.GetChromiteTrackingBranch()
        for branch in ["firmware", "factory"]:
            if tracking_branch.startswith(branch):
                saw_config_for_branch = False
                for build_name in self.site_config:
                    if build_name.endswith("-%s" % branch):
                        self.assertFalse(
                            "release" in build_name,
                            "Factory|Firmware release builders should not "
                            "contain release in their name.",
                        )
                        saw_config_for_branch = True

                self.assertTrue(
                    saw_config_for_branch,
                    "No config found for %s branch. As this is the %s branch, "
                    "all release configs that are being used must end in %s."
                    % (branch, tracking_branch, branch),
                )

    def _HasValidSuffix(self, config_name, config_types):
        """Given a config_name, see if it has a suffix in config_types.

        Args:
            config_name: Name of config to compare.
            config_types: A tuple/list of config suffixes.

        Returns:
            True, if the config has a suffix matching one of the types.
        """
        for config_type in config_types:
            if (
                config_name.endswith("-" + config_type)
                or config_name == config_type
            ):
                return True

        return False

    def testValidPrebuilts(self):
        """Verify all builders have valid prebuilt values."""
        for build_name, config in self.site_config.items():
            msg = "Config %s: has unexpected prebuilts value." % build_name
            valid_values = (False, constants.PRIVATE, constants.PUBLIC)
            self.assertTrue(config["prebuilts"] in valid_values, msg)

    def testBuildPackagesForRecoveryImage(self):
        """Tests that we build the packages required for recovery image."""
        for build_name, config in self.site_config.items():
            if "recovery" in config.images:
                if not config.packages:
                    # No packages are specified. Defaults to build all packages.
                    continue

                self.assertIn(
                    "chromeos-base/chromeos-initramfs",
                    config.packages,
                    "%s does not build chromeos-initramfs, which is required "
                    "for creating the recovery image" % build_name,
                )

    def testBuildBaseImageForRecoveryImage(self):
        """Tests that we build the packages required for recovery image."""
        for build_name, config in self.site_config.items():
            if "recovery" in config.images:
                self.assertIn(
                    "base",
                    config.images,
                    "%s does not build the base image, which is required for "
                    "building the recovery image" % build_name,
                )

    def testExternalConfigsDoNotUseInternalFeatures(self):
        """External configs should not use chrome_internal, or official.xml."""
        msg = (
            "%s is not internal, so should not use chrome_internal, or an "
            "internal manifest"
        )
        for build_name, config in self.site_config.items():
            if not config["internal"]:
                self.assertFalse(
                    "chrome_internal" in config["useflags"], msg % build_name
                )
                self.assertNotEqual(
                    config.get("manifest"),
                    constants.OFFICIAL_MANIFEST,
                    msg % build_name,
                )

    def testNoShadowedUseflags(self):
        """Configs should not have both useflags x and -x."""
        msg = "%s contains useflag %s and -%s."
        for build_name, config in self.site_config.items():
            useflag_set = set(config["useflags"])
            for flag in useflag_set:
                if not flag.startswith("-"):
                    self.assertFalse(
                        "-" + flag in useflag_set,
                        msg % (build_name, flag, flag),
                    )

    def testCheckBuilderClass(self):
        """Verify builder_class_name is a valid value."""
        for build_name, config in self.site_config.items():
            builder_class_name = config["builder_class_name"]
            if builder_class_name is None:
                continue

            cls = builders.GetBuilderClass(builder_class_name)
            self.assertTrue(
                issubclass(cls, generic_builders.Builder),
                msg="config %s has a broken builder_class_name" % build_name,
            )

    def testDistinctBoardSets(self):
        """Verify that distinct board sets are distinct."""
        boards_dict = self._GetBoardTypeToBoardsDict()
        # Every board should be in exactly one of the distinct board sets.
        for board in boards_dict["all_boards"]:
            found = False
            for s in boards_dict["distinct_board_sets"]:
                if board in s:
                    if found:
                        assert False, "%s in multiple board sets." % board
                    else:
                        found = True
            if not found:
                assert False, "%s in no board sets" % board
        for s in boards_dict["distinct_board_sets"]:
            for board in s - boards_dict["all_boards"]:
                assert False, (
                    "%s in distinct_board_sets but not in all_boards" % board
                )

    def testCanaryBuildTimeouts(self):
        """Verify we get the expected timeout values."""
        msg = "%s doesn't have expected timout: (%s != %s)"
        for build_name, config in self.site_config.items():
            if config.build_type != constants.CANARY_TYPE:
                continue
            expected = 18 * 60 * 60

            self.assertEqual(
                config.build_timeout,
                expected,
                msg % (build_name, config.build_timeout, expected),
            )

    def testBuildTimeouts(self):
        """Verify that timeout values are sensible."""
        for build_name, config in self.site_config.items():
            # Chrome infra has a hard limit of 24h.
            self.assertLessEqual(
                config.build_timeout,
                24 * 60 * 60,
                "%s timeout %s is greater than 24h"
                % (build_name, config.build_timeout),
            )

    def testLuciScheduler(self):
        """LUCI Scheduler entries only work for swarming builds."""
        for config in self.site_config.values():
            if config.schedule is not None:
                # TODO: validate the scheduler syntax.
                self.assertIsInstance(config.schedule, str)

            if config.triggered_gitiles is not None:
                self.assertEqual(
                    config.schedule,
                    "triggered",
                    "triggered_gitiles requires triggered schedule on config %s"
                    % config.name,
                )

                try:
                    for trigger in config.triggered_gitiles:
                        gitiles_url = trigger[0]
                        ref_list = trigger[1]
                        self.assertIsInstance(gitiles_url, str)
                        for ref in ref_list:
                            self.assertIsInstance(ref, str)
                        if len(trigger) > 2:
                            for path_regexp in trigger[2]:
                                self.assertIsInstance(path_regexp, str)
                except (TypeError, ValueError):
                    self.fail(
                        (
                            "%s has a triggered_gitiles that is malformed: %r\n"
                            "Simple example: [['url', ['refs/heads/main']]]"
                        )
                        % (config.name, config.triggered_gitiles)
                    )


class TemplateTest(ChromeosConfigTestBase):
    """Tests for templates."""

    def testConfigNamesMatchTemplate(self):
        """Test that all configs have names that match their templates."""
        for name, config in self.site_config.items():
            # Tryjob configs should be tested based on what they are mirrored
            # from.
            if name.endswith("-tryjob"):
                name = name[: -len("-tryjob")]

            template = config._template
            if template:
                # We mix '-' and '_' in various name spaces.
                name = name.replace("_", "-")
                template = template.replace("_", "-")
                msg = "%s should end with %s to match its template"
                self.assertTrue(name.endswith(template), msg % (name, template))

            for other in self.site_config.GetTemplates():
                if name.endswith(other) and other != template:
                    if template:
                        msg = "%s has more specific template: %s" % (
                            name,
                            other,
                        )
                        self.assertGreater(len(template), len(other), msg)
                    else:
                        msg = "%s should have %s as template" % (name, other)
                        self.assertFalse(name, msg)


class BoardConfigsTest(ChromeosConfigTestBase):
    """Tests for the per-board templates."""

    def setUp(self):
        ge_build_config = config_lib.LoadGEBuildConfigFromFile()
        boards_dict = chromeos_config.GetBoardTypeToBoardsDict(ge_build_config)

        self.external_board_configs = chromeos_config.CreateBoardConfigs(
            boards_dict, ge_build_config
        )

        self.internal_board_configs = (
            chromeos_config.CreateInternalBoardConfigs(
                self.site_config, boards_dict, ge_build_config
            )
        )

    def testBoardConfigsSuperset(self):
        """Ensure all external boards are listed as internal, also."""
        for board in self.external_board_configs:
            self.assertIn(board, self.internal_board_configs)

    def testUpdateBoardConfigs(self):
        """Test UpdateBoardConfigs."""
        pre_test = copy.deepcopy(self.internal_board_configs)
        update_boards = list(pre_test)[2:5]

        result = chromeos_config.UpdateBoardConfigs(
            self.internal_board_configs,
            update_boards,
            test_specific_flag=True,
        )

        # The source wasn't modified.
        self.assertEqual(self.internal_board_configs, pre_test)

        # The result as the same list of boards.
        self.assertCountEqual(list(result), list(pre_test))

        # And only appropriate values were updated.
        for b in pre_test:
            if b in update_boards:
                # Has new key.
                self.assertTrue(
                    result[b].test_specific_flag, "Failed in %s" % b
                )
            else:
                # Was not updated.
                self.assertEqual(result[b], pre_test[b], "Failed in %s" % b)
