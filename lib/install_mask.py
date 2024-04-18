# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Install mask used to filter files when installing binpkg into sysroot."""

# Install mask for portage ebuilds.  Used by `cros build-image` and
# strip_package.  Mask for base, dev, and test images.
DEFAULT = {
    "*.a",
    "*.c",
    "*.cc",
    "*.cmake",
    "*.go",
    "*.la",
    "*.h",
    "*.hh",
    "*.hpp",
    "*.h++",
    "*.hxx",
    "*.proto",
    "*/.keep*",
    "/build/bin",
    "/build/initramfs",
    "/build/lib",
    "/build/libexec",
    "/build/manatee",
    "/build/opt",
    "/build/rootfs/dlc",
    "/build/share",
    "/etc/init.d",
    "/etc/runlevels",
    "/etc/selinux/intermediates",
    "/etc/xinetd.d",
    "/firmware",
    "/lib/modules/*/vdso",
    "/lib/rc",
    "/opt/google/containers/android/vendor/lib*/pkgconfig",
    "/opt/google/containers/android/build",
    "/usr/bin/*-config",
    "/usr/bin/Xnest",
    "/usr/bin/Xvfb",
    "/usr/include",
    "/usr/lib/cros_rust_registry",
    "/usr/lib/debug",
    "/usr/lib/gopath",
    "/usr/lib*/pkgconfig",
    "/usr/local/autotest-chrome",
    "/usr/man",
    "/usr/share/aclocal",
    "/usr/share/applications",
    "/usr/share/cups/drv",
    "/usr/share/doc",
    "/usr/share/gettext",
    "/usr/share/gtk-2.0",
    "/usr/share/gtk-doc",
    "/usr/share/info",
    "/usr/share/man",
    "/usr/share/ppd",
    "/usr/share/openrc",
    "/usr/share/pkgconfig",
    "/usr/share/profiling",
    "/usr/share/readline",
    "/usr/src",
    "/boot/config-*",
    "/boot/System.map-*",
    "/usr/local/build/autotest",
    "/lib/modules/*/build",
    "/lib/modules/*/source",
    "test_*.ko",
}

# Mask for factory install shim (`cros build-image factory_install`).
FACTORY_SHIM = DEFAULT.union(
    {
        "/opt/google/chrome",
        "/opt/google/containers",
        "/opt/google/dlc",
        # TODO(b/303350519): Remove this mask once out of rootfs.
        "/opt/google/modemfwd-firmware",
        "/opt/google/vms",
        "/usr/lib64/dri",
        "/usr/lib/dri",
        "/usr/share/X11",
        "/usr/share/chromeos-assets/[^i]*",
        "/usr/share/chromeos-assets/i[^m]*",
        "/usr/share/fonts",
        "/usr/share/mime",
        "/usr/share/oem",
        "/usr/share/sounds",
        "/usr/share/zoneinfo",
    }
)

# Mask for images without systemd.
SYSTEMD = {
    "/lib/systemd/network",
    "/usr/lib/systemd/system",
}
