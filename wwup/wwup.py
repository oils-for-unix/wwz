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

## Soil CI

The uploaded structure we want:

    uuu.oilshell.org/
      wwup.cgi
      github-jobs/
        7783/
          benchmarks.wwz
          benchmarks.json
          benchmarks.tsv

The HTTP POST request.  There are three params:

  payload-type=soil
  subdir=github-jobs/7783
  wwz=@benchmarks.wwz

- OK might as well add the ability to upload multiple files?
  - is wwz special?  Yes because we open it up and validate it with zipfile

  file1=benchmarks.json
  file2=benchmarks.tsv

Note: it might be possible to generalize this into an array, but let's keep it
simple for now.

TODO:

- This means that 'subdir' is `github-jobs/7783` then?
  - we have to allow a slash
  - disallow path components that are . or ..
- allow raw HTML here
  - maybe allowed_exts: [] is part of the configuration

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
    'max_wwz_entries': 1000,
    # total size of .wwz is 5 MB max, to prevent people from filling up too
    # much
    'max_bytes': 5 * 1000 * 1000,
    'subdir_depth': 1,
  },

  'only-2-files': {
    'max_wwz_entries': 2,
    'max_bytes': 1000,
    'subdir_depth': 1,

    # For testing
    'allow_overwrite': True,
  },

  'only-3-bytes': {
    'max_wwz_entries': 5,
    'max_bytes': 3,
    'subdir_depth': 1,
  },

  'testing': {
    # For testing
    'allow_overwrite': True,
  },

  # Is this one policy, or multiple policies?
  'oils-ci': {
    # the 'wild' tests might exceed 1000 files and 20 MB?
    'max_wwz_entries': 1000,
    'max_bytes': 20 * 1000 * 1000,

    # subdir=github-jobs/1234
    'subdir_depth': 2,

    # disable check for extensions
    #
    # TODO: should only allow text types + "grandfathered" HTML/CSS/JS
    # HTML is still a problem because people could put links to their own site
    # on ours - we could use an HTML filter
    #
    # Follow principle of least privilage
    'check_wwz_names': False,
  }
}

def ValidateSubdir(subdir, expected_depth):
  parts = subdir.split('/')
  for part in parts:
    if part in ('', '.', '..'):
      return 'Invalid subdir part %r' % part

  depth = len(parts) 
  if depth != expected_depth:
    return 'Expected %d parts, got %d' % (expected_depth, depth)

  return None


def CopyFile(temp_file, out_path, allow_overwrite):
  if allow_overwrite:
    mode = os.O_CREAT | os.O_WRONLY
  else:
    # Fail if the file already exists
    mode = os.O_CREAT | os.O_EXCL | os.O_WRONLY

  try:
    fd = os.open(out_path, mode, 0o644)
  except OSError as e:
    raise RuntimeError('Error opening %r: %s' % (out_path, e))

  out_f = os.fdopen(fd, 'w')

  while True:
    chunk = temp_file.read(1024 * 1024)  # 1 MB at a time
    if not chunk:
      break
    out_f.write(chunk)

  out_f.close()
  temp_file.close()

  if not allow_overwrite:
    # Make it read-only too
    os.chmod(out_path, 0o444)


def DoOneFile(label, policy, environ, form_val, out_dir):
  # The cgi module stores file uploads in a temp directory (like PHP).  So we
  # read it and write it to a new location 1 MB at a time.

  #print('FILE %r' %  form_val.file)
  #print('FILEname %r' %  form_val.filename)
  if form_val.filename is None:
    raise RuntimeError('Expected %s field to be a file, not a string' % label)

  temp_file = form_val.file  # get the file handle

  os.path.splitext
  _, outer_ext = os.path.splitext(form_val.filename)

  num_wwz_entries = -1

  maybe_trailing_slash = ''  # no trailing slash for regular files

  if outer_ext == '.wwz':
    maybe_trailing_slash = '/'  # for printing URL

    try:
      z = zipfile.ZipFile(temp_file)
    except zipfile.BadZipfile as e:
      raise RuntimeError('Error opening zip: %s' % e)

    names = z.namelist()
    num_wwz_entries = len(names)

    # Low limit of 10 by default
    max_wwz_entries = policy.get('max_wwz_entries', 10)
    if num_wwz_entries > max_wwz_entries:
        raise RuntimeError('wwz has %d files, but only %d are allowed' %
            (num_wwz_entries, max_wwz_entries))

    for rel_path in names:
      # Can't have absolute paths
      if rel_path.startswith('/'):
        raise RuntimeError('Invalid path %r' % rel_path)

      # Path traversal check
      # normpath turns foo/bar/../../.. into '..'
      norm_path = os.path.normpath(rel_path)
      if norm_path.startswith('.'):
        raise RuntimeError('Invalid path %r' % rel_path)

      if policy.get('check_wwz_names', True):
        # Executable content check, e.g. disallow .html .css .jss
        if not rel_path.endswith('/'):
          _, ext = os.path.splitext(rel_path)
          if ext not in ALLOWED_EXTENSIONS:
            raise RuntimeError('Archive file %r has an invalid extension' % rel_path)

    # Important: seek back to the beginning, because ZipFile read it!
    temp_file.seek(0)

  elif outer_ext not in ALLOWED_EXTENSIONS:
    # If it's not .wwz, it must be a text file.  This doesn't respect
    # check_wwz_names.
    raise RuntimeError('File %r has an invalid extension' % form_val.filename)

  out_path = os.path.join(out_dir, form_val.filename)
  CopyFile(temp_file, out_path, policy.get('allow_overwrite', False))

  doc_root = environ['DOCUMENT_ROOT']
  rel_path = out_path[len(doc_root)+1 : ]
  http_host = environ['HTTP_HOST']

  # Trailing slash for .wwz
  url = 'https://%s/%s%s' % (http_host, rel_path, maybe_trailing_slash)

  return {
      'filename': form_val.filename,
      'num_wwz_entries': num_wwz_entries,
      'out_path': out_path,
      'url': url,
      }


def Upload(environ, form, dest_base_dir):

  # for logging
  if 0:
    print('Status: 200 OK')
    print('Content-Type: text/plain; charset=utf-8')
    print('')
    print('OK')

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

  num_bytes = int(environ['CONTENT_LENGTH'])
  # Low limit of 10_000 by default
  max_bytes = policy.get('max_bytes', 10000)
  if num_bytes > max_bytes:
      raise RuntimeError('POST body is %s bytes, but only %s are allowed' %
          (num_bytes, max_bytes))

  subdir = form.getfirst('subdir')
  if subdir is None:
    raise RuntimeError('Expected subdir')

  error_str = ValidateSubdir(subdir, policy.get('subdir_depth', 1))
  if error_str:
    raise RuntimeError('Invalid subdir %r: %s' % (subdir, error_str))

  # Now process up to 3 files: file1=  file2=  file3=
  # If the extension is .wwz, then open up the contents and validate it

  out_dir = os.path.join(dest_base_dir, payload_type, subdir)
  try:
    os.makedirs(out_dir)
  except OSError as e:
    if e.errno != errno.EEXIST:
      raise

  summaries = []

  # FieldStorage only supports 'in'
  # - it doesn't support .get()
  # - getvalue() gives a string
  if 'file1' in form:
    file1_value = form['file1']
    summaries.append(DoOneFile('file1', policy, environ, file1_value, out_dir))

  if 'file2' in form:
    file2_value = form['file2']
    summaries.append(DoOneFile('file2', policy, environ, file2_value, out_dir))

  if 'file3' in form:
    file3_value = form['file3']
    summaries.append(DoOneFile('file3', policy, environ, file3_value, out_dir))

  PrintStatusOk()

  print('Hi from wwup.cgi')
  print('')
  print('payload type = %s' % payload_type)
  print('subdir = %r' % subdir)
  print('num bytes = %r' % num_bytes)
  print('')

  for summary in summaries:
    print('summary = %r' % summary)
  print('')


def RunHook(environ, form, run_hook):
  PrintStatusOk()

  # TODO: Look up policy?

  print('TODO: Run hook %r' % run_hook)


def main(argv):
  cgitb.enable()  # Enable tracebacks

  method = os.getenv('REQUEST_METHOD', 'GET')

  if method == 'GET':
    print(r'''
wwup.cgi - HTTP uploader

Example usage:

    curl \
      --form 'payload-type=osh-runtime' \
      --form 'subdir=git-123' \
      --form 'wwz=@myfile.wwz' \
      $URL

    curl \
      --form 'payload-type=soil-ci' \
      --form 'subdir=git-123' \
      --form 'wwz=@benchmarks.wwz' \
      --form 'file1=@benchmarks.tsv' \
      --form 'file2=@benchmarks.json' \
      $URL

    curl \
      --form 'run-hook=soil-event-job-done' \
      $URL
''')
    return

  # Dumps info
  #cgi.test()

  # TODO: We could throttle here, e.g. if there are too many files

  dest_base_dir = sys.argv[1]

  form = cgi.FieldStorage(fp=sys.stdin, environ=os.environ)
  run_hook = form.getfirst('run-hook')

  try:
    if run_hook is not None:
      RunHook(os.environ, form, run_hook)
    else:
      Upload(os.environ, form, dest_base_dir)
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

# vim: sw=2


