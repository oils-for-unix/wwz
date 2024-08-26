#!/usr/bin/env bash
#
# Usage:
#   ./run.sh <function name>

set -o nounset
set -o pipefail
set -o errexit

readonly HOST=uuu.oilshell.org
readonly DIR=uuu.oilshell.org

#readonly WWUP_URL=http://uuu.oilshell.org/wwup.cgi

# Redirecting to HTTPS, which is annoying
readonly WWUP_URL=https://uuu.oilshell.org/wwup.cgi

banner() {
  echo ---
  echo "$@"
  echo
}

setup() {
  # Matches params in wwup.cgi

  # /uuu/ for for 'untrusted user uploads'
  ssh $HOST "mkdir -v -p $DIR/uuu"
}

upload-overwrite() {
  banner 'upload-overwrite'
  curl \
    --include \
    --form 'payload-type=only-2-files' \
    --form 'subdir=git-133' \
    --form 'file1=@_tmp/overwrite.wwz' \
    $WWUP_URL
}

upload-multiple() {
  banner 'Bad outer filename'
  curl \
    --include \
    --form 'payload-type=testing' \
    --form 'subdir=multiple-456' \
    --form 'file1=@_tmp/notzip' \
    $WWUP_URL

  banner 'upload-multiple'
  curl \
    --include \
    --form 'payload-type=testing' \
    --form 'subdir=multiple-456' \
    --form 'file1=@_tmp/one.wwz' \
    --form 'file2=@_tmp/extra.json' \
    --form 'file3=@_tmp/extra.tsv' \
    $WWUP_URL
}

upload-one() {
  banner 'upload-one'
  curl \
    --include \
    --form 'payload-type=osh-runtime' \
    --form 'subdir=git-133' \
    --form 'file1=@_tmp/one.wwz' \
    $WWUP_URL
}

upload-bad-type() {
  banner 'Missing payload type'
  curl \
    --form 'subdir=git-123' \
    --form 'file1=@_tmp/one.wwz' \
    $WWUP_URL

  banner 'Invalid payload type'
  curl \
    --form 'payload-type=yyy' \
    --form 'subdir=git-123' \
    --form 'file1=@_tmp/one.wwz' \
    $WWUP_URL
}

upload-bad-subdir() {
  banner 'Missing subdir'
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'file1=@_tmp/one.wwz' \
    $WWUP_URL

  banner 'Invalid subdir'
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'subdir=/root' \
    --form 'file1=@_tmp/one.wwz' \
    $WWUP_URL

  banner 'Invalid subdir with too many parts'
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'subdir=one/two' \
    --form 'file1=@_tmp/one.wwz' \
    $WWUP_URL
}

upload-bad-zip() {
  banner 'Missing wwz field'
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'subdir=git-123' \
    $WWUP_URL

  # --trace-ascii - shows the POST body
  banner 'wwz field is a string rather than a file'
  #curl --trace-ascii - \
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'subdir=git-123' \
    --form 'wwz=some-string' \
    $WWUP_URL

  echo x > _tmp/notzip
  banner 'wwz field is not a zip file'
  #curl --trace-ascii - \
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'subdir=git-123' \
    --form 'file1=@_tmp/notzip' \
    $WWUP_URL
}

upload-disallowed() {
  # invalid file extension
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'subdir=git-123' \
    --form 'file1=@_tmp/bad.wwz' \
    $WWUP_URL

  # dir traversal
  curl \
    --form 'payload-type=osh-runtime' \
    --form 'subdir=git-123' \
    --form 'file1=@_tmp/bad2.wwz' \
    $WWUP_URL

  curl \
    --form 'payload-type=only-2-files' \
    --form 'subdir=git-123' \
    --form 'file1=@_tmp/one.wwz' \
    $WWUP_URL

  curl \
    --form 'payload-type=only-3-bytes' \
    --form 'subdir=git-123' \
    --form 'file1=@_tmp/one.wwz' \
    $WWUP_URL
}

get-request() {
  curl --include \
    $WWUP_URL
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

  # Include dir entry for _tmp
  zip $wwz _tmp/ _tmp/{osh-runtime,shell-id,host-id}/* 

  unzip -l $wwz
  echo

  local wwz2=_tmp/overwrite.wwz
  rm -f -v $wwz2

  date > _tmp/overwrite.txt
  zip $wwz2 _tmp/overwrite.txt
  unzip -l $wwz2
  echo

  echo '{"hi": 42}' > _tmp/extra.json
  echo 'one' > _tmp/extra.tsv

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
  CONTENT_LENGTH=0 ./wwup.cgi
  CONTENT_LENGTH=0 REQUEST_METHOD=POST ./wwup.cgi < /dev/null
}

inherit-test() {
  scp inherit-test.cgi $HOST:$DIR

  set -x
  curl http://uuu.oilshell.org/inherit-test.cgi
  echo

  #curl --trace-ascii - \
  curl \
    --form foo=bar http://uuu.oilshell.org/inherit-test.cgi
}

deploy() {
  scp wwup.{py,cgi} $HOST:$DIR
}

demo() {
  deploy

  get-request
  echo status=$?
  echo

  set +o errexit
  upload-bad-type
  echo status=$?
  echo

  #return

  upload-bad-subdir
  echo status=$?
  echo

  upload-bad-zip
  echo status=$?
  echo

  upload-disallowed
  echo status=$?
  echo

  upload-overwrite
  echo status=$?
  echo

  upload-one
  echo status=$?
  echo

  upload-multiple
  echo status=$?
  echo
}

hook-hello() {
  banner 'Invalid hook'
  curl \
    --include \
    --form 'run-hook=zzz' \
    $WWUP_URL

  banner 'Error in hook / misconfigured hook'
  # TODO: the file is not executable, etc.  It returns status 1
  curl \
    --include \
    --form 'run-hook=bad-hook' \
    $WWUP_URL

  banner 'hook-hello'

  curl \
    --include \
    --form 'run-hook=soil-web-hello' \
    --form 'arg1=arg1' \
    --form 'arg2=arg2' \
    $WWUP_URL

}

hook-demo() {
  deploy

  hook-hello
}

"$@"
