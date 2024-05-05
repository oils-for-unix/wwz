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

FLUP_PATH=_tmp/flup-1.0.3.dev-20110405 
TEST_DIR=_tmp/wwz-test

unit() {
  PYTHONPATH=$FLUP_PATH ./wwz_test.py
}

make-testdata() {
  mkdir -p _wwz/{dir,no-index,empty-dir}  # input data
  # .wwz is just a zip file?  Compression can be changed later?

  # I guess zip files have a magic number so it's OK to change it.

  echo '<p>index.html</p>' > _wwz/index.html
  echo '<p>wwz</p>' > _wwz/foo.html
  echo '{"wwz": 1}'      > _wwz/foo.json
  echo 'PNG'     > _wwz/foo.png
  echo 'wwz txt'     > _wwz/foo.txt
  echo 'wwz no extension'      > _wwz/dir/foo
  echo '<p>dir/index.html</p>' > _wwz/dir/index.html
  echo 'no-index' > _wwz/no-index/file.txt
  tar --create --file _wwz/test.tar _wwz/*

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

  echo '---'
  echo "path_info = $suffix"
  echo

  mkdir -p _tmp/logs
  PYTHONPATH=$FLUP_PATH ./wwz.py _tmp/logs | tee $TEST_DIR/out.txt

  verify-response $TEST_DIR/out.txt 

  echo
}

cgi_first_re='^Status: (200|302|400|404)'

verify-response() {
  local response=$1

  read -r line < $response

  if [[ $line =~ $cgi_first_re ]]; then
    echo "good: $line"
    return
  fi

  echo "FAILED: first line = $line"
  return 1
}

cgi-test() {
  mkdir -p $TEST_DIR

  rm -f _tmp/logs/*

  # TODO: assert HTTP status, headers, body

  # Uncomment to test the logging ability.
  #export WWZ_REQUEST_LOG=1
  #export WWZ_TRACE_LOG=1

  # wwz not found
  run-wwz $PWD /testdata/foo.wwz /a/b/c

  run-wwz $PWD /testdata/test.wwz /
  run-wwz $PWD /testdata/test.wwz /foo.html
  run-wwz $PWD /testdata/test.wwz /foo.json
  run-wwz $PWD /testdata/test.wwz /foo.png
  run-wwz $PWD /testdata/test.wwz /foo.txt
  run-wwz $PWD /testdata/test.wwz /dir/foo
  run-wwz $PWD /testdata/test.wwz /dir/
  run-wwz $PWD /testdata/test.wwz /test.tar

  # Should print an index of files
  run-wwz $PWD /testdata/test.wwz /wwz-index
  run-wwz $PWD /testdata/test.wwz /dir/wwz-index

  # Should redirect to wwz-index
  run-wwz $PWD /testdata/test.wwz /no-index/

  run-wwz $PWD /testdata/test.wwz /no-index/wwz-index

  run-wwz $PWD /testdata/test.wwz /empty-dir/wwz-index

  # Does flup catch this?  Doesn't look like it, so let's be paranoid and more
  # We don't want people to inject headers
  run-wwz $PWD /testdata/test.wwz $'/bad\nCookie: zzz/'

  # file not found in wwz
  run-wwz $PWD /testdata/test.wwz /not-a-file

  # dir not found in wwz.  This will always redirect to wwz-index because of
  # trailing slash, but meh that's fine
  run-wwz $PWD /testdata/test.wwz /not-a-dir/

  run-wwz $PWD /testdata/test.wwz /wwz-status

  wc -l _tmp/logs/*
}

all() {
  cgi-test
  unit
}

"$@"
