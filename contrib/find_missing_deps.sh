#!/bin/bash -e
# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

if [[ "$#" != 1 ]] || [[ "$1" == '-h' ]]; then
  cat <<<"Usage: $0 <category>/<package>

This is a helper script that does the following:
1) Get a list of all shared libraries provided by the specified package.
2) Get a rough list of all packages that need any of those shared libraries.
3) Print a list of any of those packages that do not DEPEND or RDPEND on the
   specified package.

If you set the BOARD environment variable, this will run against that target.
"
  exit 1
fi

root="/"
equery="equery"
package="$1"

if [[ -n "${BOARD}" ]]; then
  root="/build/${BOARD}/"
  equery="equery-${BOARD}"
fi

search_path="${root}var/db/pkg/"

mapfile -t shared_libs < <(
  "${equery}" f "${package}" | grep '\.so' | grep -v 'debug$' \
    | xargs basename -a
)
if [[ "${#shared_libs[@]}" == "0" ]]; then
  exit 0
fi

get_grep_pattern() {
  local first="$1"
  shift
  printf %s "${first}" "${@/#/\\|}"
}
grep_for="$(get_grep_pattern "${shared_libs[@]}")"

# shellcheck disable=SC2038,SC2185 # TODO: rewrite find
mapfile -t reverse_needed < <(
  find "${search_path}" -iname NEEDED -exec grep -l "\b${grep_for}\b" {} + \
    | xargs dirname
)
if [[ "${#reverse_needed[@]}" == "0" ]]; then
  exit 0
fi

grep -sL "${package}" "${reverse_needed[@]/%/\/DEPEND}" \
  "${reverse_needed[@]/%/\/RDEPEND}" \
  | awk -F/ '{
  cmd = "qatom -q -C -F \"%{CATEGORY}/%{PN} %{PV} %{PR}\" " $(NF-2)"/"$(NF-1)
  cmd | getline formatted_package
  close(cmd)
  print formatted_package " " $(NF)
}' | grep -v "^${package} " | sort
