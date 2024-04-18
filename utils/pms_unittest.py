# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""PMS tests."""

import pytest

from chromite.utils import pms


def test_reject_invalid_versions():
    """Check we reject invalid versions."""
    assert not pms.version_valid("\n1.2")
    assert not pms.version_valid("1.2\n")
    assert not pms.version_valid("1.2\n1.3")


def test_versions_eq():
    """Check equal versions compared correctly."""
    assert pms.version_eq("1", "1")
    assert pms.version_eq("1.000", "1.0")
    assert pms.version_eq(
        "1_alpha1_beta2_pre3_rc4_p5", "1_alpha1_beta2_pre3_rc4_p5"
    )
    assert pms.version_eq("1.2.3.200702020000", "1.2.3.200702020000")
    assert pms.version_eq("1.2.3_alpha", "1.2.3_alpha0-r0")
    assert pms.version_eq("1.2.3_alpha4-r5", "1.2.3_alpha4-r5")


def test_versions_eq_invalid():
    """Check invalid versions throw correctly."""
    with pytest.raises(ValueError) as e:
        pms.version_eq("1\n", "1")
    assert "Invalid version" in str(e)

    with pytest.raises(ValueError) as e:
        pms.version_eq("1", "1\n")
    assert "Invalid version" in str(e)


def test_version_lt():
    """Test a variety of unequal versions using LT."""
    # Version varieties.
    assert pms.version_lt("1", "2")
    assert pms.version_lt("1.0", "2.0")
    assert pms.version_lt("1.1.1", "1.1.1.1")
    assert pms.version_lt("1.034", "1.1")
    assert pms.version_lt("1.0.1", "1.002")
    assert pms.version_lt("0.0.1", "0.0.2")
    assert pms.version_lt("1.2.3.200702020000", "1.2.3.200702020001")
    # Letter components.
    assert pms.version_lt("20004", "20004a")
    assert pms.version_lt("1b", "1z")
    # Suffix checks.
    assert pms.version_lt("2.0_pre", "2.0")
    assert pms.version_lt("2.0_alpha", "2.0_beta")
    assert pms.version_lt("2.0_beta", "2.0_pre")
    assert pms.version_lt("2.0_pre", "2.0_rc")
    assert pms.version_lt("2.0_rc", "2.0_p")
    assert pms.version_lt("2.0_pre", "2.0_pre1")
    assert pms.version_lt("2.0_pre", "2.0_p1234")
    assert pms.version_lt("2.0_rc", "2.0")
    assert pms.version_lt("2.0", "2.0_p")
    assert pms.version_lt("1_alpha_beta", "1_alpha")
    assert pms.version_lt("1_alpha_beta", "1_alpha1")
    assert pms.version_lt("1_alpha_beta", "1_beta")
    assert pms.version_lt("1_alpha_beta", "1_alpha_beta1")
    assert pms.version_lt("1_alpha_beta_pre", "1_alpha_beta")
    assert pms.version_lt("1_alpha_beta", "1_alpha_beta_p")
    assert pms.version_lt("2.0_rc", "2.0_rc_p")
    # Revisions.
    assert pms.version_lt("1.0", "1.0-r1")
    assert pms.version_lt("1.0-r5", "1.0-r10")


def test_version_gt():
    """Test a few of the LT cases in reverse to do a quick GT check."""
    assert pms.version_gt("1.1.1.1", "1.1.1")
    assert pms.version_gt("2.0_p1234", "2.0_pre")
    assert pms.version_gt("2.0", "2.0_rc")
    assert pms.version_gt("1_alpha_beta_p", "1_alpha_beta")
