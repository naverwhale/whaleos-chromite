# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Hostname utilities."""

import logging
import socket


GOOGLE_HOSTNAME_SUFFIX = (".google.com", ".googler.com", ".googlers.com")


def get_host_name(fully_qualified=False):
    """Return hostname of current machine, with domain if |fully_qualified|."""
    hostname = socket.gethostname()
    try:
        hostname = socket.gethostbyaddr(hostname)[0]
    except (socket.gaierror, socket.herror) as e:
        logging.warning(
            "please check your /etc/hosts file; resolving your hostname"
            " (%s) failed: %s",
            hostname,
            e,
        )

    if fully_qualified:
        return hostname
    else:
        return hostname.partition(".")[0]


def get_host_domain():
    """Return domain of current machine.

    If there is no domain, return 'localdomain'.
    """

    hostname = get_host_name(fully_qualified=True)
    domain = hostname.partition(".")[2]
    return domain if domain else "localdomain"


def host_is_ci_builder(fq_hostname=None, golo_only=False, gce_only=False):
    """Return True iff a host is a continuous-integration builder.

    Args:
        fq_hostname: The fully qualified hostname. By default, we fetch it for
            you.
        golo_only: Only return True if the host is in the Chrome Golo. Defaults
            to False.
        gce_only: Only return True if the host is in the Chrome GCE block.
            Defaults to False.
    """
    CORP_DOMAIN = "corp.google.com"
    GOLO_DOMAIN = "golo.chromium.org"
    CHROME_DOMAIN = "chrome." + CORP_DOMAIN
    CHROMEOS_BOT_INTERNAL = "chromeos-bot.internal"

    if not fq_hostname:
        fq_hostname = get_host_name(fully_qualified=True)
    in_golo = fq_hostname.endswith("." + GOLO_DOMAIN)
    in_gce = fq_hostname.endswith("." + CHROME_DOMAIN) or fq_hostname.endswith(
        "." + CHROMEOS_BOT_INTERNAL
    )
    if golo_only:
        return in_golo
    elif gce_only:
        return in_gce
    else:
        return in_golo or in_gce


def is_google_host():
    """Checks if the code is running on google host."""

    hostname = get_host_name(fully_qualified=True)
    return hostname.endswith(GOOGLE_HOSTNAME_SUFFIX)
