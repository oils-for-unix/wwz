#!/usr/bin/env python2
from __future__ import print_function
"""
wwup.cgi

Upload untrusted user content.

- Validate the uploaded data
  - Only data files like .txt .tsv .csv .json are allowed.
  - No web content like .html .css .js.
  - Maybe enforce naming?
    - Directory is /U/$payload_type
    - e.g. /U/osh-runtime/git-$commit/$client_name.wwz
      - git-commit enforces that it's a real build
      - $client_name could be the machine name, or it could also be
        github-actions.$machine and sourcehut.$machine
      - can also be $user.machine
        - github actions uses 'runner', container is 'uke'
        - sourcehut is 'build'
        - we can test based on env vars
    - cleanup will sort by 'last modified' timestamp I guess

- Control resource usage
  - Limit the size of each upload
  - Delete old files automatically
  - Check total size and space perhaps?

- Run aggregation hooks
  - Concatenate TSV files for easier analysis
  - Generate HTML with trusted binaries

- Type of aggregation
  - across machines for a different commit

  - then DIFF by COMMIT

## Notes on streaming / temp files

cgi.py uses a temp file for the entire POST body.  But each file in the
multipart form payload is buffered into a StringIO object.

So we

1. write that in-memory file to another temporary directory
2. make it read-only
3. atomically rename it onto the destination.  If this fails, the file was
already uploaded.

We could use something like 'python-multipart' to stream the upload.

But for now we can just reject files with CONTENT_LENGTH greater than a certain
amount.

"""

import cgi
import cgitb
import cStringIO
import errno
import os
import sys
import tempfile
import zipfile


def PrintStatusOk():
  print('Status: 200 OK')
  print('Content-Type: text/plain; charset=utf-8')
  print('')


# Debug before main()
if 1:
  PrintStatusOk()


def log(msg, *args):
  if args:
    msg = msg % args
  print(msg, file=sys.stderr)


# Hard-coded payload validation:

# definitely no .js .css .html
ALLOWED_EXTENSIONS = ['.txt', '.tsv', '.csv', '.json']

# Rules by payload:

PAYLOADS = {
  'osh-runtime': {
    # How should we check these patterns, if at all?
    #
    # - Each pattern matches some file?
    # - The patterns cover ALL data uploaded - probably too strict, since we
    #   have other files
    'globs': [
      'osh-runtime/*.tsv',  # times, provenance, gc-stats
      'shell-id/*-*/*.txt',
      'host-id/*-*/*.txt',
    ],

    # loose sanity check on .wwz
    'max_files': 1000,
    # total size of .wwz is 5 MB max, to prevent people from filling up too
    # much
    'max_bytes': 5 * 1000 * 1000,
  },

  'only-2-files': {
    'max_files': 2,
    'max_bytes': 1000,
  },

  'only-3-bytes': {
    'max_files': 5,
    'max_bytes': 3,
  },

  # Is this one policy, or multiple policies?
  'oils-ci': {
  }
}


def Upload(dest_base_dir, tmp_dir):
  # Dumps info
  #cgi.test()

  # for logging
  if 0:
    print('Status: 200 OK')
    print('Content-Type: text/plain; charset=utf-8')
    print('')
    print('OK')

  form = cgi.FieldStorage(fp=sys.stdin, environ=os.environ)

  # Form field examples:
  # - payload-type=osh-runtime
  # - subdir=git-1ab435d
  # - wwz=@foo.wwz

  payload_type = form.getfirst('payload-type')
  if payload_type is None:
    raise RuntimeError('Expected payload type')

  policy = PAYLOADS.get(payload_type)
  if policy is None:
    raise RuntimeError('Invalid payload type %r' % payload_type)

  subdir = form.getfirst('subdir')
  if subdir is None:
    raise RuntimeError('Expected subdir')

  if '/' in subdir:
    raise RuntimeError('Invalid subdir %r' % subdir)

  # The cgi module stores file uploads in a temp directory (like PHP).  So we
  # read it and write it to a new location 1 MB at a time.

  # FieldStorage only supports 'in'
  # - it doesn't support .get()
  # - getvalue() gives a string
  if 'wwz' not in form:
    raise RuntimeError('Expected wwz field')
  wwz_value = form['wwz']

  #print('FILE %r' %  wwz_value.file)
  #print('FILEname %r' %  wwz_value.filename)
  if wwz_value.filename is None:
    raise RuntimeError('Expected wwz field to be a file, not a string')

  temp_file = wwz_value.file  # get the file handle

  temp_file.seek(0, os.SEEK_END)
  num_bytes = temp_file.tell()
  max_bytes = policy['max_bytes']
  if num_bytes > max_bytes:
      raise RuntimeError('wwz is %d bytes, but only %d are allowed' %
          (num_bytes, max_bytes))

  temp_file.seek(0)

  try:
    z = zipfile.ZipFile(temp_file)
  except zipfile.BadZipfile as e:
    raise RuntimeError('Error opening zip: %s' % e)

  names = z.namelist()
  num_files = len(names)

  max_files = policy['max_files']
  if num_files > max_files:
      raise RuntimeError('wwz has %d files, but only %d are allowed' %
          (num_files, max_files))

  for rel_path in names:
    # Can't have absolute paths
    if rel_path.startswith('/'):
      raise RuntimeError('Invalid path %r' % rel_path)

    # Path traversal check
    # normpath turns foo/bar/../../.. into '..'
    norm_path = os.path.normpath(rel_path)
    if norm_path.startswith('.'):
      raise RuntimeError('Invalid path %r' % rel_path)

    # Executable content check, e.g. disallow .html .css .jss
    _, ext = os.path.splitext(rel_path)
    if ext not in ALLOWED_EXTENSIONS:
      raise RuntimeError('File %r has an invalid extension' % rel_path)

  # Important: seek back to the beginning, because ZipFile read it!
  temp_file.seek(0)

  out_dir = os.path.join(dest_base_dir, payload_type, subdir)
  try:
    os.makedirs(out_dir)
  except OSError as e:
    if e.errno != errno.EEXIST:
      raise
  out_path = os.path.join(out_dir, wwz_value.filename)

  with open(out_path, 'w') as out_f:
    while True:
      chunk = temp_file.read(1024 * 1024)  # 1 MB at a time
      if not chunk:
        break
      out_f.write(chunk)

  out_f.close()
  temp_file.close()

  PrintStatusOk()

  print('Hi from wwup.cgi')
  print('')
  print('payload type = %s' % payload_type)
  print('subdir = %r' % subdir)
  print('filename = %r' % wwz_value.filename)
  print('num files = %r' % num_files)
  print('num bytes = %r' % num_bytes)
  print('')

  print('Wrote to %r' % out_path)
  print('')

  for rel_path in names:
    print('%r' % rel_path)


def main(argv):
  cgitb.enable()  # Enable tracebacks

  method = os.getenv('REQUEST_METHOD', 'GET')

  if method == 'GET':
    print(r'''
wwwup.cgi - HTTP uploader

Example usage:

    curl \
      --form 'payload-type=osh-runtime' \
      --form 'subdir=git-123' \
      --form 'wwz=@myfile.wwz' \
      $URL
''')
    return

  # TODO: We could throttle here, e.g. if there are too many files

  dest_base_dir = sys.argv[1]
  tmp_dir = sys.argv[2]

  try:
    Upload(dest_base_dir, tmp_dir)
  except RuntimeError as e:
    # CGI has a Status: header!
    print('Status: 400 Bad Request')
    print('Content-Type: text/plain; charset=utf-8')
    print('')
    print('Bad request: %s' % e)

  # Logging
  # - How long did it take to upload the file?
  # - How big was it?
  # - How long did it take to run the aggregation and HTML hooks?

  # TODO:
  # - Delete old files here, according to policy

  # Now run ~/bin/wwup-hooks/osh-runtime.sh
  #
  # Can be stored in soil/wwup-hooks/
  # soil/web.sh deploy currently makes soil-web/, which should be turned into
  # a wwup-hook.
  #
  # Policy:
  # - Executables in the repo cannot generate HTML/JS/CSS web content.
  # - Only executables we control and deploy manually.

  print('Done wwup.cgi')


if __name__ == '__main__':
  main(sys.argv)
