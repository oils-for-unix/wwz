#!/usr/bin/env bash
#
# Usage:
#   ./admin.sh <function name>

set -o nounset
set -o pipefail
set -o errexit

readonly ROOT=~/travis-ci.oilshell.org

setup() {
  mkdir -v -p $ROOT/untrusted	  
}

upload-one() {
  curl --form 'file=@README.md' http://travis-ci.oilshell.org/wwup.cgi
}

upload-many() {
  # The [] thing is what the browser sends?
  curl \
    --form 'files[]=@README.md' \
    --form 'files[]=@hello.cgi' \
    --form 'files2=@hello.cgi' \
    --form 'files2=@run.sh' \
    http://travis-ci.oilshell.org/wwup.cgi
}

demo() {
  cp -v wwup.cgi $ROOT
  upload-many
}

"$@"
