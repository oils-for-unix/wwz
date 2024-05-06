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
    --include \
    --form 'payload-type=osh-runtime' \
    --form 'wwz=@_tmp/one.wwz' \
    $URL
}

upload-bad-type() {
  # missing
  curl \
    --form 'wwz=@_tmp/one.wwz' \
    http://travis-ci.oilshell.org/wwup.cgi

  # bad
  curl \
    --form 'payload-type=yyy' \
    --form 'wwz=@_tmp/one.wwz' \
    http://travis-ci.oilshell.org/wwup.cgi
}

upload-bad-zip() {
  # missing
  curl \
    --form 'payload-type=osh-runtime' \
    http://travis-ci.oilshell.org/wwup.cgi

  # not a zip file
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'wwz=@README.md' \
    http://travis-ci.oilshell.org/wwup.cgi
}

upload-disallowed() {
  # invalid file extension
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'wwz=@_tmp/bad.wwz' \
    http://travis-ci.oilshell.org/wwup.cgi

  curl \
    --form 'payload-type=really-small' \
    --form 'wwz=@_tmp/one.wwz' \
    http://travis-ci.oilshell.org/wwup.cgi
}

make-zips() {
  rm -r -f -v _tmp/*
  mkdir -p _tmp/{osh-runtime,shell-id,host-id,bad,other}

  for file in \
    _tmp/osh-runtime/aa.tsv \
    _tmp/shell-id/bb.txt \
    _tmp/host-id/cc.txt \
    _tmp/bad/bad.js \
    _tmp/other/zz.txt;
  do
     echo x > $file
  done

  local wwz=_tmp/one.wwz
  rm -f -v $wwz

  zip $wwz _tmp/{osh-runtime,shell-id,host-id}/*
  unzip -l $wwz
  echo

  local bad=_tmp/bad.wwz
  rm -f -v $bad

  cp $wwz $bad
  zip $bad _tmp/bad/*
  unzip -l $bad
  echo
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

  upload-disallowed
  echo status=$?
  echo

  set -x
  upload-one
  echo status=$?
  echo
}

"$@"
