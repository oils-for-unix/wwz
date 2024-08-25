#!/usr/bin/env bash
#
# Usage:
#   ./git.sh <function name>

set -o nounset
set -o pipefail
set -o errexit

log-main() {
  git log main..
}

diff-main() {
  git diff main..
}

rebase-main() {
  git rebase -i main
}

merge-to-main() {
  local branch
  branch=$(git rev-parse --abbrev-ref HEAD)

  git checkout main
  git merge $branch
  git push
  git checkout $branch
}

"$@"
