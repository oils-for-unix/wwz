#!/usr/bin/env bash
#
# Usage:
#   ./admin.sh <function name>

set -o nounset
set -o pipefail
set -o errexit

readonly HOST=travis-ci.oilshell.org
readonly DIR=travis-ci.oilshell.org

setup() {
  # /U/ for for 'untrusted user uploads'
  ssh $HOST "mkdir -v -p $DIR/U"
}

readonly URL=http://travis-ci.oilshell.org/wwup.cgi

upload-one() {
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'zip=@_tmp/one.zip' \
    $URL
}

upload-bad-type() {
  # missing
  curl \
    --form 'zip=@_tmp/one.zip' \
    http://travis-ci.oilshell.org/wwup.cgi

  # bad
  curl \
    --form 'payload-type=zzz' \
    --form 'zip=@_tmp/one.zip' \
    http://travis-ci.oilshell.org/wwup.cgi
}

upload-bad-zip() {
  # missing
  curl \
    --form 'payload-type=osh-runtime' \
    http://travis-ci.oilshell.org/wwup.cgi

  # bad
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'zip=@README.md' \
    http://travis-ci.oilshell.org/wwup.cgi
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

make-zips() {
  mkdir -p _tmp/{osh-runtime,shell-id,host-id,bad}

  for file in \
    _tmp/osh-runtime/aa.tsv \
    _tmp/shell-id/bb.txt \
    _tmp/host-id/cc.txt \
    _tmp/host-id/bad.js \
    _tmp/bad/zz.txt;
  do
     echo x > $file
  done

  rm -f -v _tmp/one.zip

  zip _tmp/one.zip _tmp/{osh-runtime,shell-id,host-id,bad}/*

  unzip -l _tmp/one.zip
}

local-test() {
  # I guess I should pass upload dir
  ./wwup.cgi
}

demo() {
  scp wwup.cgi $HOST:$DIR

  set +o errexit
  upload-bad-type
  echo status=$?
  echo

  upload-bad-zip
  echo status=$?
  echo

  upload-one
  echo status=$?
  echo
}

"$@"
