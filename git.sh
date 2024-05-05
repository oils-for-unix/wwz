#!/usr/bin/env bash
#
# Usage:
#   ./git.sh <function name>

set -o nounset
set -o pipefail
set -o errexit

diff-master() {
  git diff master..
}

rebase-master() {
  git rebase -i master
}

merge-to-master() {
  local branch
  branch=$(git rev-parse --abbrev-ref HEAD)

  git checkout master
  git merge $branch
  git push
  git checkout $branch
}

"$@"
