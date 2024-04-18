# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Configuration and fixtures for pytest.

See the following doc link for an explanation of conftest.py and how it is used
by pytest:
https://docs.pytest.org/en/latest/explanation/fixtures.html
"""

from __future__ import division

import multiprocessing
import os
from unittest import mock

import pytest

import chromite as cr
from chromite.lib import cidb
from chromite.lib import constants
from chromite.lib import cros_test_lib
from chromite.lib import osutils
from chromite.lib import parallel
from chromite.lib import retry_stats
from chromite.lib.parser import package_info

# We use wildcard imports here to make fixtures defined in the test module
# globally visible.
# pylint: disable=unused-wildcard-import, wildcard-import
#
# Importing from *_fixtures.py files into conftest.py is the only time a
# module should use a wildcard import. *_fixtures.py files should ensure
# that the only items visible to a wildcard import are pytest fixtures,
# usually by declaring __all__ if necessary.
from chromite.test.portage_fixtures import *


@pytest.fixture(scope="class", autouse=True)
def mock_cidb_connection():
    """Ensure that the CIDB connection factory is initialized as a mock.

    Unit tests should never connect to any live instances of CIDB and this
    initialization ensures that they only ever get a mock connection instance.

    Previously cros_test_lib.TestProgram.runTests was responsible for globally
    initializing this mock and multiple tests are flaky if this mock connection
    is not initialized before any tests are run.
    """
    # pylint: disable=protected-access
    cidb.CIDBConnectionFactory._ClearCIDBSetup()
    cidb.CIDBConnectionFactory.SetupMockCidb()


@pytest.fixture(scope="class", autouse=True)
def assert_no_zombies():
    """Assert that tests have no active child processes after completion.

    This assertion runs after class tearDown methods because of the
    scope='class' declaration.
    """
    yield
    children = multiprocessing.active_children()
    if children:
        pytest.fail(
            "Test has %s active child processes after tearDown: %s"
            % (len(children), children)
        )


@pytest.fixture(scope="class", autouse=True)
def clear_retry_stats_manager():
    """Reset the global state of the stats manager before every test.

    Without this fixture many tests fail due to this global value being set and
    then not cleared. The child manager process may have been killed but this
    module level variable is still pointing at it, leading to the test trying to
    write to a closed pipe.
    """
    # pylint: disable=protected-access
    retry_stats._STATS_COLLECTION = None


@pytest.fixture(autouse=True)
def set_testing_environment_variables():
    """Sets a standard environment, and ensures often-used state is restored."""
    # Use a `mock.patch` ContextManager to snapshot and restore the entire dict.
    with mock.patch.dict(os.environ):
        # Set environment marker to relax certain strict checks for test code.
        os.environ["CHROMITE_INSIDE_PYTEST"] = "1"

        # Force all log lines in tests to include ANSI color prefixes, since it
        # can be configured per-user.
        os.environ["NOCOLOR"] = "no"

        # Clear environment variables that chromite is globally sensitive to and
        # that should be suppressed for tests.
        os.environ.pop(constants.SHARED_CACHE_ENVVAR, None)

        yield


@pytest.fixture
def singleton_manager(monkeypatch):
    """Force tests to use a singleton Manager and automatically clean it up."""
    m = parallel.Manager()

    def our_manager():
        return m

    monkeypatch.setattr(parallel, "Manager", our_manager)
    yield
    m.shutdown()


@pytest.fixture
def legacy_capture_output(request, capfd):
    """Adds the `capfd` fixture to TestCase-style test classes.

    This fixture should only be used on cros_test_lib.TestCase test classes,
    since it doesn't yield anything and just attaches the built-in pytest
    `capfd` fixture to the requesting class. Tests written as standalone
    functions should use pytest's built-in `capfd` fixture instead of this. See
    the documentation for more information on how to use the `capfd` fixture
    that this provides:
    https://docs.pytest.org/en/latest/reference/reference.html#std-fixture-capfd

    See the following documentation for an explanation of why fixtures have to
    be provided to TestCase classes in this manner:
    https://docs.pytest.org/en/latest/how-to/unittest.html#mixing-pytest-fixtures-into-unittest-testcase-subclasses-using-marks
    """
    request.cls.capfd = capfd


@pytest.fixture
def testcase_caplog(request, caplog):
    """Adds the `caplog` fixture to TestCase-style test classes.

    This fixture should only be used on cros_test_lib.TestCase test classes,
    since it doesn't yield anything and just attaches the built-in pytest
    `caplog` fixture to the requesting class. Tests written as standalone
    functions should use pytest's built-in `caplog` fixture instead of this. See
    the documentation for more information on how to use the `caplog` fixture
    that this provides:
    https://docs.pytest.org/en/latest/reference/reference.html#caplog

    See the following documentation for an explanation of why fixtures have to
    be provided to TestCase classes in this manner:
    https://docs.pytest.org/en/latest/how-to/unittest.html#mixing-pytest-fixtures-into-unittest-testcase-subclasses-using-marks
    """
    request.cls.caplog = caplog


@pytest.fixture
def testcase_monkeypatch(request, monkeypatch):
    """Adds the `monkeypatch` fixture to TestCase-style test classes.

    This fixture should only be used on cros_test_lib.TestCase test classes,
    since it doesn't yield anything and just attaches the built-in pytest
    `monkeypatch` fixture to the requesting class. Tests written as standalone
    functions should use pytest's built-in `monkeypatch` fixture instead of
    this. See the documentation for more information on how to use the
    `monkeypatch` fixture that this provides:
    https://docs.pytest.org/en/latest/reference/reference.html#monkeypatch

    See the following documentation for an explanation of why fixtures have to
    be provided to TestCase classes in this manner:
    https://docs.pytest.org/en/latest/how-to/unittest.html#mixing-pytest-fixtures-into-unittest-testcase-subclasses-using-marks
    """
    request.cls.monkeypatch = monkeypatch


def pytest_assertrepr_compare(op, left, right):
    """Global hook for defining detailed explanations for failed assertions.

    https://docs.pytest.org/en/latest/how-to/assert.html
    """
    if (
        isinstance(left, package_info.CPV)
        and isinstance(right, cr.test.Overlay)
        and op == "in"
    ):
        package_path = right.path / left.category / left.package
        return [
            f"{left.pv}.ebuild exists in {right.path}",
            "Ebuild does not exist in overlay.",
            "Ebuilds found in overlay with same category and package:",
        ] + sorted(
            "\t" + str(p.relative_to(package_path))
            for p in package_path.glob("*.ebuild")
        )


def pytest_addoption(parser):
    """Adds additional options to the default pytest CLI args."""
    parser.addoption(
        "--no-chroot",
        dest="chroot",
        action="store_false",
        help="Skip any tests that require a chroot to function.",
    )


def pytest_collection_modifyitems(config, items):
    """Modifies the list of test items pytest has collected.

    See the following link for full documentation on pytest collection hooks:
    https://docs.pytest.org/en/latest/reference/reference.html#collection-hooks
    """
    if config.option.chroot:
        return
    skip_inside_only = pytest.mark.skip(reason="Test requires a chroot to run.")
    for item in items:
        if "inside_only" in item.keywords:
            item.add_marker(skip_inside_only)


@pytest.fixture
def run_mock():
    """Robust mock for cros_build_lib.run."""
    with cros_test_lib.RunCommandMock() as rc_mock:
        rc_mock.SetDefaultCmdResult()
        yield rc_mock


@pytest.fixture(scope="session", autouse=True)
def _check_network_test(request):
    """Detect whether the test uses network_test marker.

    This can be helpful for code to detect when network traffic is attempted but
    network tests weren't requested which indicates a bad test -- one that needs
    to be decorated with @cros_test_lib.pytestmark_network_test.
    """
    for item in request.session.items:
        if item.get_closest_marker("network_test") is not None:
            cros_test_lib.NETWORK_TESTS_ENABLED = True
            break


@pytest.fixture
def tmp_path_cleanup_sudo(tmp_path):
    """A tmp_path, but safely handles cleanup of contents created with sudo.

    This fixture will chown all contents back to the current user once finished,
    allowing the contents to be removed if pytest decides to do so.
    """
    yield tmp_path

    if tmp_path.exists():
        osutils.Chown(
            tmp_path, user=os.geteuid(), group=os.getegid(), recursive=True
        )
