# Copyright 2017 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Baselines for user/group tests."""

from typing import NamedTuple, Set

from chromite.lib import constants


class UserEntry(NamedTuple):
    """User details matching typical account database (e.g. /etc/passwd).

    Example GECOS entry:
    firewall:!:236:236:firewall daemon:/dev/null:/bin/false
    """

    user: str
    encpasswd: str = "!"
    uid: int = None
    gid: int = None
    home: str = "/dev/null"
    shell: str = "/bin/false"


class GroupEntry(NamedTuple):
    """Group details matching typical account database (e.g. /etc/group).

    Example GECOS entry:
    tty:!:5:xorg,power,brltty
    """

    group: str
    encpasswd: str = "!"
    gid: int = None
    users: Set[str] = set()


# For users that we allow to login to the system, allow a number of alternative
# shells.  These are equivalent from a security POV.
_VALID_LOGIN_SHELLS = set(
    (
        "/bin/sh",
        "/bin/bash",
        "/bin/dash",
    )
)

# Pulled out for COIL disabling.
_SCANNER_DAEMON = "saned"  # nocheck

USER_BASELINE = dict(
    (e.user, e)
    for e in (
        # These are sorted by uid.
        UserEntry(
            user="root",
            encpasswd="x",
            uid=0,
            gid=0,
            home="/root",
            shell=_VALID_LOGIN_SHELLS,
        ),
        UserEntry(user="bin", uid=1, gid=1, home="/bin"),
        UserEntry(user="daemon", uid=2, gid=2, home="/sbin"),
        UserEntry(user="adm", uid=3, gid=4, home="/var/adm"),
        UserEntry(user="lp", uid=4, gid=7, home="/var/spool/lpd"),
        UserEntry(user="news", uid=9, gid=13, home="/var/spool/news"),
        UserEntry(user="uucp", uid=10, gid=14, home="/var/spool/uucp"),
        # CrOS system daemon UIDs.
        UserEntry(user="sshd", uid=204, gid=204),
        UserEntry(user="tss", uid=207, gid=207, home="/var/lib/tpm"),
        UserEntry(user="dhcp", uid=224, gid=224),
        UserEntry(
            user="goofy",
            encpasswd="x",
            uid=248,
            gid=248,
            home="/home/goofy",
            shell="/bin/bash",
        ),
        UserEntry(
            user="portage",
            uid=constants.PORTAGE_UID,
            gid=constants.PORTAGE_GID,
            home="/var/tmp/portage",
        ),
        UserEntry(
            user="chronos",
            encpasswd="x",
            uid=1000,
            gid=1000,
            home="/home/chronos/user",
            shell=_VALID_LOGIN_SHELLS,
        ),
        UserEntry(user="chronos-access", uid=1001, gid=1001),
        UserEntry(user="user-containers", uid=10000, gid=10000),
        UserEntry(user="nobody", uid=65534, gid=65534),
        UserEntry(user="android-root", uid=655360, gid=655360),
    )
)

USER_BASELINE_TERMINA = dict(
    (e.user, e)
    for e in (
        # These are sorted by uid.
        UserEntry(user="lxd", uid=298, gid=298),
    )
)

USER_BOARD_BASELINES = {
    "tael": USER_BASELINE_TERMINA,
    "tatl": USER_BASELINE_TERMINA,
}

GROUP_BASELINE = dict(
    (e.group, e)
    for e in (
        # These are sorted by gid.
        GroupEntry(group="root", gid=0, users={"root"}),
        GroupEntry(group="bin", gid=1, users={"root", "bin", "daemon"}),
        GroupEntry(group="daemon", gid=2, users={"root", "bin", "daemon"}),
        GroupEntry(group="sys", gid=3, users={"root", "bin", "adm"}),
        GroupEntry(group="adm", gid=4, users={"root", "adm", "daemon"}),
        GroupEntry(group="tty", gid=5, users={"power", "brltty", "bootsplash"}),
        GroupEntry(
            group="disk",
            gid=6,
            users={
                "root",
                "adm",
                "cros-disks",
                "fwupd",
                "cros_healthd",
                "image-burner",
            },
        ),
        GroupEntry(
            group="lp",
            gid=7,
            users={
                "lp",
                "lpadmin",
                "cups",
                "chronos",
                "printscanmgr",
            },
        ),
        GroupEntry(group="mem", gid=8),
        GroupEntry(group="kmem", gid=9),
        GroupEntry(group="wheel", gid=10, users={"root"}),
        GroupEntry(group="floppy", gid=11, users={"root"}),
        GroupEntry(group="news", gid=13, users={"news"}),
        GroupEntry(group="uucp", gid=14, users={"uucp", "gpsd"}),
        GroupEntry(group="console", gid=17),
        GroupEntry(
            group="audio",
            gid=18,
            users={
                "cras",
                "chronos",
                "volume",
                "midis",
                "sound_card_init",
                "rtanalytics",
            },
        ),
        GroupEntry(group="cdrom", gid=19, users={"cros-disks"}),
        GroupEntry(group="tape", gid=26, users={"root"}),
        GroupEntry(
            group="video",
            gid=27,
            users={
                "root",
                "chronos",
                "arc-camera",
                "dlm",
                "rtanalytics",
                "crosvm",
                "cfm-monitor",
                "smdisplay",
                "cdm-oemcrypto",
                "cros_healthd",
                "nvpd",
                "ml-core",
                "runtime_probe",
                "fwupd",
            },
        ),
        GroupEntry(group="cdrw", gid=80, users={"cros-disks"}),
        GroupEntry(
            group="usb",
            gid=85,
            users={"mtp", "brltty", "dlm", "modem", "fwupd"},
        ),
        GroupEntry(group="users", gid=100),
        # CrOS system daemon GIDs.
        GroupEntry(
            group="tss",
            gid=207,
            users={
                "root",
                "attestation",
                "bootlockboxd",
                "chaps",
                "oobe_config_restore",
                "oobe_config_save",
                "tpm_manager",
                "trunks",
                "u2f",
            },
        ),
        GroupEntry(
            group="pkcs11",
            gid=208,
            users={"root", "vpn", "chronos", "chaps", "wpa", "attestation"},
        ),
        GroupEntry(group="wpa", gid=219, users={"root"}),
        GroupEntry(
            group="input",
            gid=222,
            users={"cras", "power", "chronos", "healthd_evdev"},
        ),
        GroupEntry(group="dhcp", gid=224, users={"shill"}),
        GroupEntry(group="brltty", gid=240, users={"chronos"}),
        GroupEntry(group="modem", gid=241, users={"shill"}),
        GroupEntry(group="goofy", gid=248, users={"goofy"}),
        GroupEntry(
            group="portage", gid=constants.PORTAGE_GID, users={"portage"}
        ),
        GroupEntry(
            group="preserve",
            gid=253,
            users={"root", "attestation", "tpm_manager", "rollback_cleanup"},
        ),
        GroupEntry(group="scanner", gid=255, users={_SCANNER_DAEMON}),
        GroupEntry(
            group="uinput", gid=258, users={"bluetooth", "volume", "biod"}
        ),
        GroupEntry(group="apmanager", gid=259, users={"apmanager", "buffet"}),
        GroupEntry(
            group="peerd", gid=260, users={"buffet", "chronos", "peerd"}
        ),
        GroupEntry(
            group="buffet", gid=264, users={"chronos", "buffet", "power"}
        ),
        GroupEntry(group="webservd", gid=266, users={"buffet", "webservd"}),
        GroupEntry(
            group="lpadmin",
            gid=269,
            users={
                "cups",
                "lpadmin",
                "printscanmgr",
            },
        ),
        # FUSE-based filesystem daemons.
        GroupEntry(
            group="policy-readers",
            gid=303,
            users={
                "attestation",
                "chronos",
                "hardware_verifier",
                "secagentd",
                "shill",
                "u2f",
                "flex_hwis",
            },
        ),
        GroupEntry(group="fuse-drivefs", gid=304, users={"chronos"}),
        GroupEntry(group="rmtfs", gid=306, users={"rmtfs", "shill"}),
        # Groups with no associated user.
        GroupEntry(
            group="daemon-store",
            gid=400,
            users={"biod", "chaps", "crosvm", "shill"},
        ),
        GroupEntry(group="logs-access", gid=401, users={"debugd-logs"}),
        GroupEntry(group="serial", gid=402, users={"uucp"}),
        GroupEntry(group="hidraw", gid=403, users={"fwupd", "fwupdate-hidraw"}),
        GroupEntry(
            group="i2c",
            gid=404,
            users={"fwupdate-i2c", "fwupdate-drm_dp_aux-i2c", "fwupd", "power"},
        ),
        GroupEntry(group="apex-access", gid=405, users={"rtanalytics"}),
        GroupEntry(group="utmp", gid=406),
        GroupEntry(
            group="drm_dp_aux",
            gid=407,
            users={"fwupdate-drm_dp_aux", "fwupdate-drm_dp_aux-i2c", "fwupd"},
        ),
        GroupEntry(
            group="tun",
            gid=413,
            users={"crosvm", "patchpaneld", "shill", "vpn", "wpan"},
        ),
        GroupEntry(group="gpio", gid=414, users={"modem"}),
        GroupEntry(group="suzy-q", gid=415, users={"chronos", "rma_fw_keeper"}),
        GroupEntry(
            group="cros_ec-access",
            gid=416,
            users={
                "runtime_probe",
                "healthd_ec",
                "power",
                "typecd_ec",
                "rgbkbd",
            },
        ),
        GroupEntry(
            group="rgbkbd", gid=20186, users={"rgbkbd", "power", "fwupd"}
        ),
        GroupEntry(group="virtaccess", gid=418, users={"crosvm", "wilco_dtc"}),
        GroupEntry(
            group="crash-access", gid=419, users={"crash", "secanomaly"}
        ),
        GroupEntry(
            group="crash-user-access",
            gid=420,
            users={"crash", "chronos", "vm_cicerone"},
        ),
        GroupEntry(
            group="pstore-access",
            gid=422,
            users={"debugd", "oobe_config_restore"},
        ),
        GroupEntry(
            group="bluetooth-audio", gid=423, users={"bluetooth", "cras"}
        ),
        GroupEntry(group="ppp", gid=424, users={"shill", "vpn"}),
        GroupEntry(
            group="cras",
            gid=600,
            users={
                "chronos",
                "crosvm",
                "power",
                "rtanalytics",
                "sound_card_init",
            },
        ),
        GroupEntry(
            group="fpdev",
            gid=426,
            users={
                "biod",
                "healthd_fp",
            },
        ),
        GroupEntry(
            group="wayland", gid=601, users={"chronos", "crosvm", "pluginvm"}
        ),
        GroupEntry(group="arc-bridge", gid=602, users={"chronos"}),
        GroupEntry(group="arc-camera", gid=603, users={"chronos", "crosvm"}),
        GroupEntry(
            group="camera",
            gid=20042,
            users={"arc-camera", "cfm-firmware-updaters", "fwupd"},
        ),
        GroupEntry(
            group="debugfs-access",
            gid=605,
            users={"arc-camera", "shill", "power", "metrics", "traced-probes"},
        ),
        GroupEntry(group="midis", gid=608, users={"chronos"}),
        GroupEntry(
            group="password-viewers",
            gid=611,
            users={"kerberosd", "shill", "system-proxy"},
        ),
        GroupEntry(group="ml-core", gid=612, users={"ml-core", "arc-camera"}),
        GroupEntry(group="chronos", gid=1000),
        GroupEntry(
            group="chronos-access",
            gid=1001,
            users={
                "vpn",
                "chronos",
                "cros-disks",
                "imageloaderd",
                "crash",
                "dlp",
                "image-burner",
                "seneschal",
                "spaced",
            },
        ),
        GroupEntry(
            group="user-containers", gid=10000, users={"user-containers"}
        ),
        # More CrOS system daemon GIDs.
        GroupEntry(
            group="ippusb",
            gid=20100,
            users={"ippusb", "lp", "lpadmin", "cups", _SCANNER_DAEMON},
        ),
        GroupEntry(
            group="cfm-peripherals",
            gid=20103,
            users={"cfm-monitor", "cfm-firmware-updaters"},
        ),
        GroupEntry(group="shill", gid=20104, users={"shill"}),
        GroupEntry(group="pluginvm", gid=20128, users={"crosvm", "pluginvm"}),
        GroupEntry(
            group="kerberosd", gid=20131, users={"kerberosd", "kerberosd-exec"}
        ),
        GroupEntry(
            group="cups-proxy",
            gid=20136,
            users={"crosvm", "cups-proxy", "pluginvm"},
        ),
        GroupEntry(
            group="usbprinter",
            gid=20155,
            users={
                "cups",
                _SCANNER_DAEMON,
            },
        ),
        GroupEntry(group="hotline", gid=20157, users={"hotline", "hotlog"}),
        GroupEntry(
            group="traced-producer",
            gid=20162,
            users={"traced", "traced-probes", "chronos", "crosvm"},
        ),
        GroupEntry(
            group="traced-consumer",
            gid=20164,
            users={"traced", "chronos", "debugd"},
        ),
        GroupEntry(group="vpn", gid=20174, users={"vpn", "shill"}),
        GroupEntry(group="frecon", gid=20203, users={"frecon", "bootsplash"}),
        GroupEntry(group="nogroup", gid=65533),
        GroupEntry(group="nobody", gid=65534),
        GroupEntry(
            group="android-everybody",
            gid=665357,
            users={"chronos", "cros-disks", "seneschal"},
        ),
        GroupEntry(group="android-root", gid=655360, users={"android-root"}),
        GroupEntry(group="nvpd", gid=20190, users={"nvpd"}),
        GroupEntry(
            group="missived_senders",
            gid=20191,
            users={"cros_healthd", "secagentd", "secanomaly"},
        ),
        GroupEntry(group="secagentd", gid=20192, users={"secagentd"}),
        GroupEntry(
            group="disk-dlc",
            gid=20777,
            users={"root", "dlcservice", "imageloaderd"},
        ),
        GroupEntry(
            group="shadercached",
            gid=333,
            users={"shadercached", "crosvm"},
        ),
        GroupEntry(
            group="crosvm",
            gid=299,
            users={"crosvm", "shadercached", "spaced"},
        ),
        GroupEntry(group="mei-access", gid=427, users={"healthd_psr"}),
        GroupEntry(
            group="oobe_config",
            gid=428,
            users={
                "oobe_config_save",
                "oobe_config_restore",
                "rollback_cleanup",
            },
        ),
        GroupEntry(
            group="mmc_service", gid=20208, users={"mmc_service", "bluetooth"}
        ),
    )
)

GROUP_BASELINE_TERMINA = dict(
    (e.group, e)
    for e in (
        # These are sorted by gid.
        GroupEntry(group="lxd", gid=298, users={"lxd", "chronos"}),
    )
)

GROUP_BOARD_BASELINES = {
    "tael": GROUP_BASELINE_TERMINA,
    "tatl": GROUP_BASELINE_TERMINA,
}
