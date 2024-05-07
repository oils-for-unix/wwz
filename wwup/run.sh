#!/usr/bin/env bash
#
# Usage:
#   ./admin.sh <function name>

set -o nounset
set -o pipefail
set -o errexit

readonly HOST=travis-ci.oilshell.org
readonly DIR=travis-ci.oilshell.org

banner() {
  echo ---
  echo "$@"
  echo
}

setup() {
  # /U/ for for 'untrusted user uploads'
  ssh $HOST "mkdir -v -p $DIR/U"
}

readonly URL=http://travis-ci.oilshell.org/wwup.cgi

upload-one() {
  curl \
    --include \
    --form 'payload-type=osh-runtime' \
    --form 'subdir=git-123' \
    --form 'wwz=@_tmp/one.wwz' \
    $URL
}

upload-bad-type() {
  banner 'Missing payload type'
  curl \
    --form 'subdir=git-123' \
    --form 'wwz=@_tmp/one.wwz' \
    http://travis-ci.oilshell.org/wwup.cgi

  banner 'Invalid payload type'
  curl \
    --form 'payload-type=yyy' \
    --form 'subdir=git-123' \
    --form 'wwz=@_tmp/one.wwz' \
    http://travis-ci.oilshell.org/wwup.cgi
}

upload-bad-subdir() {
  banner 'Missing subdir'
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'wwz=@_tmp/one.wwz' \
    http://travis-ci.oilshell.org/wwup.cgi

  banner 'Invalid subdir'
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'subdir=/root' \
    --form 'wwz=@_tmp/one.wwz' \
    http://travis-ci.oilshell.org/wwup.cgi
}

upload-bad-zip() {
  banner 'Missing wwz field'
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'subdir=git-123' \
    http://travis-ci.oilshell.org/wwup.cgi

  # --trace-ascii - shows the POST body
  banner 'wwz field is a string rather than a file'
  #curl --trace-ascii - \
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'subdir=git-123' \
    --form 'wwz=some-string' \
    http://travis-ci.oilshell.org/wwup.cgi

  echo x > _tmp/notzip
  banner 'wwz field is not a zip file'
  #curl --trace-ascii - \
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'subdir=git-123' \
    --form 'wwz=@_tmp/notzip' \
    http://travis-ci.oilshell.org/wwup.cgi
}

upload-disallowed() {
  # invalid file extension
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'subdir=git-123' \
    --form 'wwz=@_tmp/bad.wwz' \
    http://travis-ci.oilshell.org/wwup.cgi

  # dir traversal
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'subdir=git-123' \
    --form 'wwz=@_tmp/bad2.wwz' \
    http://travis-ci.oilshell.org/wwup.cgi

  curl \
    --form 'payload-type=only-2-files' \
    --form 'subdir=git-123' \
    --form 'wwz=@_tmp/one.wwz' \
    http://travis-ci.oilshell.org/wwup.cgi

  curl \
    --form 'payload-type=only-3-bytes' \
    --form 'subdir=git-123' \
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

  # - Python 2.7.4 extractall() has a check for dir traversal
  # - unzip on my Linux box does too
  # - But we can still check for this
  local bad2=_tmp/bad2.wwz
  rm -f -v $bad2

  cp $wwz $bad2
  zip $bad2 ../testdata/zip-dir-traversal.txt
  unzip -l $bad2
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

  upload-bad-subdir
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
