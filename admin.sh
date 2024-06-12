#!/usr/bin/env bash
#
# Usage:
#   ./admin.sh <function name>

set -o nounset
set -o pipefail
set -o errexit

# Needed for flup!
# Should put this in the wwz dir!  Along with flup itself

download-setuptools() {
  wget --no-clobber --directory ~/src \
    https://files.pythonhosted.org/packages/5e/bc/70a3d8213cda12eac84c770895c54521d0d19847b512cef54d6c83b0ddcb/setuptools-0.6c9.tar.gz
}

download-flup() {
  mkdir -p _tmp
  wget --directory _tmp \
    https://pypi.python.org/packages/9c/34/c1e3f35c5bc08ea53749f523f5285f2ae7d192cf5838a298c0339ae9c804/flup-1.0.3.dev-20110405.tar.gz
}

build-flup() {
  cd _tmp
  tar -x -z < flup*.tar.gz
  cd flup*/
  python2 setup.py build
}

smoke-test() {
  ### See if we can import flup successfully

  mkdir -p _tmp/logs
  PYTHONPATH=_tmp/flup-1.0.3.dev-20110405 ./wwz.py _tmp/logs
}

kill-wwz() {
  ### Sometimes you need to do this after redeploying.

  # Particularly if you MUTATE a .wwz file.  It's better to create new ones.

  killall -v wwz.py
}

"$@"
