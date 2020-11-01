#!/bin/bash
#
# Test the FastCGI script without a server.
#
# Usage:
#   ./wwz-test.sh <function name>
#
# Example:
# 
#   ./wwz-test.sh make-testdata  # make a zip file
#   ./wwz-test.sh all            # make various requests against it

set -o nounset
set -o pipefail
set -o errexit

make-testdata() {
  mkdir -p _wwz/dir  # input data
  # .wwz is just a zip file?  Compression can be changed later?

  # I guess zip files have a magic number so it's OK to change it.

  echo '<p>index.html</p>' > _wwz/index.html
  echo '<p>wwz</p>' > _wwz/foo.html
  echo '{"wwz": 1}'      > _wwz/foo.json
  echo 'PNG'     > _wwz/foo.png
  echo 'wwz txt'     > _wwz/foo.txt
  echo 'wwz no extension'      > _wwz/dir/foo
  echo '<p>dir/index.html</p>' > _wwz/dir/index.html

  mkdir -p testdata
  local out=$PWD/testdata/test.wwz

  rm -f $out

  pushd _wwz 
  zip -r $out .
  popd
  unzip -l $out
}


run-wwz() {
  local doc_root=$1
  local wwz_path=$2
  local suffix=$3

  # The last 4 vars seem to be required by flup's WSGIServer
  export \
    DOCUMENT_ROOT=$doc_root \
    REQUEST_URI="$wwz_path$suffix" \
    PATH_INFO=$suffix \
    REQUEST_METHOD='GET' \
    SERVER_NAME='fake-server.org' \
    SERVER_PORT='80' \
    SERVER_PROTOCOL='HTTP/1.1' \

  mkdir -p _tmp/logs
  PYTHONPATH=_tmp/flup-1.0.3.dev-20110405 ./wwz.py _tmp/logs
}

all() {
  rm -f _tmp/logs/*

  # Uncomment to test the tracing ability.
  export WWZ_REQUEST_LOG_DIR=_tmp/logs
  #export WWZ_TRACE_LOG_DIR=_tmp/logs

  # wwz not found
  run-wwz $PWD /testdata/foo.wwz /a/b/c

  run-wwz $PWD /testdata/test.wwz /
  run-wwz $PWD /testdata/test.wwz /foo.html
  run-wwz $PWD /testdata/test.wwz /foo.json
  run-wwz $PWD /testdata/test.wwz /foo.png
  run-wwz $PWD /testdata/test.wwz /foo.txt
  run-wwz $PWD /testdata/test.wwz /dir/foo
  run-wwz $PWD /testdata/test.wwz /dir/

  # file not found in wwz
  run-wwz $PWD /testdata/test.wwz /not-a-file
  # dir not found in wwz
  run-wwz $PWD /testdata/test.wwz /not-a-dir/

  wc -l _tmp/logs/*
}

"$@"
