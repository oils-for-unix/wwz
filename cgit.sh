#!/usr/bin/env bash
#
# Usage:
#   ./cgit.sh <function name>

set -o nounset
set -o pipefail
set -o errexit

download() {
  wget --no-clobber --directory-prefix _tmp \
    https://git.zx2c4.com/cgit/snapshot/cgit-1.2.3.tar.xz
}

extract() {
  pushd _tmp
  tar -x --xz < cgit-*.xz
  popd
}

# Build instructions in README
# and Makefile

readonly SRC_DIR=_tmp/cgit-1.2.3

build() {
  local makefile_override=${1:-mb-cgit.conf}

  cp -v $makefile_override $SRC_DIR/cgit.conf

  pushd $SRC_DIR

  # build with git version
  make get-git
  echo

  make

  popd
}

install() {
  pushd $SRC_DIR
  make install
  popd
}

smoke-test() {
  local dir=~/cgit

  ls -l $dir

  # Hm this is 9.6 MB!
  file $dir/cgit.cgi

  PATH_INFO=/  $dir/cgit.cgi
}

"$@"
