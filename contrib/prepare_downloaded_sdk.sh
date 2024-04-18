#!/bin/bash
# Copyright 2022 The ChromiumOS Authors.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# shellcheck disable=SC2155 # (declare and assign separately)

print_usage() {
  echo "Usage: $0 path/to/chromiumos"
  echo ""
  echo "This command will prepare downloaded checkout and chroot for"
  echo "entering by creating a user with appropriate permissions,"
  echo "fixing files' ownership, mode, defining env variables."
  echo "This is useful for sharing CrOS SDKs between developers when"
  echo "we need to debug issues."
}

if [[ "$#" -ne 1 ]]; then
  print_usage
  exit 1
fi

export SOURCE_ROOT="$1"
RELATIVE_CHROOT_ROOT="${SOURCE_ROOT}/chroot"
export CHROOT_ROOT=$(realpath "${RELATIVE_CHROOT_ROOT}")

if [[ ! -d "${SOURCE_ROOT}" ]]; then
  echo "Cannot access provided SOURCE_ROOT: ${SOURCE_ROOT}"
  print_usage
  exit 1
fi

export TARGET_USER="${USER}"

export TARGET_USER_ID="$(id -u)"

if [[ "${TARGET_USER_ID}" -eq 0 ]]; then
  echo "ERROR: run this script without sudo."
  exit 1
fi

export SDK_USER_ID=$(stat -c %u "${SOURCE_ROOT}")
export SDK_USER_GID=$(stat -c %g "${SOURCE_ROOT}")
export SDK_USER_GROUP=$(stat -c %G "${SOURCE_ROOT}")

if [[ "${SDK_USER_ID}" == "${TARGET_USER_ID}" ]]; then
  echo "Cannot determine original sdk owner."
  echo "Try deleting the checkout and re-extract the archive (with sudo)."
  exit 1
fi

export LOCAL_MOUNTS_FILE="${SOURCE_ROOT}/src/scripts/.local_mounts"
export HOME_DIR_IN="/home/${TARGET_USER}"
export HOME_DIR_OUT="${CHROOT_ROOT}${HOME_DIR_IN}"

fix_permissions() {
  # Files owned by root, nobody, portage, etc should stay that way.
  # Files owned by original SDK owner, should change to script user.
  echo "Changing owner of files with uid ${SDK_USER_ID} to ${TARGET_USER_ID}."
  find -H "${SOURCE_ROOT}" -uid "${SDK_USER_ID}" -exec \
    chown --no-dereference "${TARGET_USER_ID}" {} + 2>/dev/null
  # If we are to do this with gid, we'd have to to enumerate unknown groups
  # inside of chroot, as there are multiple. Does not seem mandatory.
}

add_user() {
  echo "Adding user ${TARGET_USER}(${TARGET_USER_ID}) in chroot."
  chroot "${CHROOT_ROOT}" bash -c \
    "useradd -m -d ${HOME_DIR_IN} ${TARGET_USER} --uid ${TARGET_USER_ID}"
  groupmod -R "${CHROOT_ROOT}" -a -U "${TARGET_USER}" portage
  groupmod -R "${CHROOT_ROOT}" -a -U "${TARGET_USER}" "${SDK_USER_GROUP}"
  groupmod -R "${CHROOT_ROOT}" -a -U "${TARGET_USER}" wheel
}

give_user_sudo() {
  SUDOERS_FILE="${CHROOT_ROOT}/etc/sudoers"
  echo "Giving ${TARGET_USER} passwordless sudo rights."
  printf "\n%s ALL=(ALL) NOPASSWD: ALL\n" "${TARGET_USER}" \
    | sudo tee -a "${SUDOERS_FILE}"
}

override_portage_user() {
  BASHRC_FILE="${HOME_DIR_OUT}/.bashrc"
  printf "\nexport PORTAGE_USERNAME=%s\n" "${TARGET_USER}" \
    | sudo tee -a "${BASHRC_FILE}"
}

make_homedir_executable() {
  chmod og+rx "${HOME_DIR_OUT}"
}

print_local_mounts() {
  # ".local_mounts may be the reason for user issue being investigated,
  # so the keep the file, but inform.
  if [[ -s "${LOCAL_MOUNTS_FILE}" ]]; then
    echo ".local_mounts file is detected. Missing mounts will cause warnings."
    echo ".local_mounts contents:"
    cat "${LOCAL_MOUNTS_FILE}"
  fi
}

print_how_to_enter() {
  echo
  echo "To enter the prepared cros_sdk:"
  echo "  (outside) cd ${SOURCE_ROOT}; cros_sdk"
}

FUNCS_TO_RUN=(
  fix_permissions
  add_user
  give_user_sudo
  override_portage_user
  make_homedir_executable
)

sudo -E bash -c "$(declare -f "${FUNCS_TO_RUN[@]}"); \
  for f in ${FUNCS_TO_RUN[*]}; do \${f}; done"

print_local_mounts
print_how_to_enter
