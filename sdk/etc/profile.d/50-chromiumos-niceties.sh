#!/bin/bash
# Copyright 2021 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Niceties for interactive logins. (cr) denotes this is a chroot, the
# __git_branch_ps1 prints current git branch in ./ . The  behavior is to
# make sure we don't reset the previous 0 value which later formats in
# $PS1 might rely on.

source /usr/share/git/git-prompt.sh

# Add a way to get the "m" branch from repo easily; used by __git_branch_ps1()
#
# Repo maintains a phony 'm/' remote using the current manifest branch name.
# This will retrieve it.
__git_m_branch() {
  git --git-dir="/mnt/host/source/.repo/manifests.git" config \
    branch.default.merge | cut -d/ -f3-
}

# A "subclass" of __git_ps1 that adds the manifest branch name into the prompt.
# ...if you're on manifest branch "0.11.257.B" and local branch "lo" and
# pass " (%s)", we'll output " (0.11.257.B/lo)".  Note that we'll never show
# the manifest branch 'main', since it's so common.
__git_branch_ps1() {
  local format_str="${1:- (%s)}"
  local m_branch
  m_branch=$(__git_m_branch)
  # Do not print the default branch names.
  case "${m_branch}" in
    "" | main | master | stable) ;;
    *)
      # shellcheck disable=SC2059
      format_str=$(printf "${format_str}" "${m_branch}/%s")
      ;;
  esac
  # for subshells, prefix the prompt with the shell nesting level.
  local lshlvl=""
  [[ -n "${SHLVL##*[!0-9]*}" ]] && [[ ${SHLVL} -gt 1 ]] && lshlvl="${SHLVL} "
  __git_ps1 "${lshlvl}${format_str}"
}

# Prompt functions should not error when in subshells.
export -f __git_ps1
export -f __git_m_branch
export -f __git_branch_ps1

PS1='$(r=$?; __git_branch_ps1 "(%s) "; exit ${r})'"${PS1}"
PS1="(cr) ${PS1}"
