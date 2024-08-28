#!/usr/bin/env python2
from __future__ import print_function
"""
wwup.cgi - HTTP uploader and "hook" runner

Features:

- Atomically rename to final destination
- Validate the uploaded data
  - text content like .txt .tsv .csv .json is safe
  - No web content like .html .css .js.
    - .wwz is grandfathered - it only recognizes file types too
  - enforces directory structure

- Control resource usage
  - Total size of each file
  - Number of entires in the .wwz file
- TODO: Delete old files automatically

- Run hooks
  - Concatenate TSV files for easier analysis
  - Generate HTML with trusted binaries

## Soil CI

The uploaded structure we want:

    ci.oilshell.org/
      uuu/                    # uploaded by wwup
        wwup.cgi
        github-jobs/
          7783/
            benchmarks.wwz
            benchmarks.json
            benchmarks.tsv
      code/                   # uploaded by SSH only
        git-$hash/
          oils-for-unix.tar
"""

import cgi
import cgitb
import cStringIO
import errno
import os
import pwd
import subprocess
import sys
import tempfile
import zipfile


def PrintStatusOk():
  print('Status: 200 OK')
  print('Content-Type: text/plain; charset=utf-8')
  print('')


def PrintError400():
  """Client error"""
  print('Status: 400 Bad Request')
  print('Content-Type: text/plain; charset=utf-8')
  print('')


def PrintError500():
  """Server error"""
  print('Status: 500 Internal Server Error')
  print('Content-Type: text/plain; charset=utf-8')
  print('')


# Debug before main()
if 0:
  PrintStatusOk()


def log(msg, *args):
  if args:
    msg = msg % args
  print(msg, file=sys.stderr)


# Hard-coded payload validation:

# definitely no .js .css .html
ALLOWED_EXTENSIONS = ['.txt', '.tsv', '.csv', '.json']

# Not using this to upload tar files
# ALLOWED_EXTENSIONS.append('.tar')

# Rules by payload:

PAYLOADS = {
  'only-2-files': {
    'max_wwz_entries': 2,
    'max_bytes': 1000,
    'subdir_depth': 1,
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

  # Policy for jobs uploading .wwz, .tsv, .json
  'github-jobs': {
    # wild.wwz has 21K files; benchmarks.wwz task has 3450 files
    'max_wwz_entries': 22000,
    # wild.wwz is 23 MB
    'max_bytes': 30 * 1000 * 1000,

    # subdir=github-jobs/1234
    'subdir_depth': 1,

    # sourcehut / Github Actions can retry tasks
    'allow_overwrite': True,

    # disable check for extensions
    #
    # TODO: should only allow text types + "grandfathered" HTML/CSS/JS
    # HTML is still a problem because people could put links to their own site
    # on ours - we could use an HTML filter
    #
    # Follow principle of least privilage
    'check_wwz_names': False,
  },

  'status-api': {
    # status-api/ has github/$RUN_ID/ and then dummy.status.txt
    'subdir_depth': 2,
    # sourcehut / Github Actions can retry tasks
    'allow_overwrite': True,
  },
}

# Copy this policy for now
PAYLOADS['sourcehut-jobs'] = PAYLOADS['github-jobs']

HOOKS = {
    'local-test': {
      'argv0': 'git/oilshell/oil/soil/web.sh',
      'argv_prefix': ['hello'],
    },

    'soil-web-hello': {
      'argv0': 'soil-web/soil/web.sh',
      'argv_prefix': ['hello'],
    },

    'soil-event-job-done': {
      # If the path is relative, it's relative to $HOME
      'argv0': 'soil-web/soil/web.sh',
      # the user can pass arbitrary args as URL params
      'argv_prefix': ['event-job-done'],
    },

    'soil-cleanup-status-api': {
      # If the path is relative, it's relative to $HOME
      'argv0': 'soil-web/soil/web.sh',
      # the user can pass arbitrary args as URL params
      'argv_prefix': ['cleanup-status-api'],
    },
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


# Notes on streaming / temp files
# 
# cgi.py uses a temp file for the entire POST body.  But each file in the
# multipart form payload is buffered into a StringIO object.
# 
# So we
# 
# 1. write that in-memory file to another temporary directory
# 2. make it read-only
# 3. atomically rename it onto the destination.  If this fails, the file was
#    already uploaded.
# 
# We could use something like 'python-multipart' to stream the upload.
# 
# But for now we can just reject files with CONTENT_LENGTH greater than a
# certain amount.

def CopyFile(input_f, out_path):
  # Fail if the file already exists
  mode = os.O_CREAT | os.O_EXCL | os.O_WRONLY

  try:
    fd = os.open(out_path, mode, 0o644)
  except OSError as e:
    raise RuntimeError('Error opening %r: %s' % (out_path, e))

  out_f = os.fdopen(fd, 'w')

  while True:
    chunk = input_f.read(1024 * 1024)  # 1 MB at a time
    if not chunk:
      break
    out_f.write(chunk)

  out_f.close()
  input_f.close()


def DoOneFile(param_name, policy, environ, form_val, out_dir):
  # The cgi module stores file uploads in a temp directory (like PHP).  So we
  # read it and write it to a new location 1 MB at a time.

  if form_val.filename is None:
    raise RuntimeError('Expected %r param to be a file, not a string' % param_name)

  input_f = form_val.file  # get the file handle

  os.path.splitext
  _, outer_ext = os.path.splitext(form_val.filename)

  num_wwz_entries = -1

  maybe_trailing_slash = ''  # no trailing slash for regular files

  if outer_ext == '.wwz':
    maybe_trailing_slash = '/'  # for printing URL

    try:
      z = zipfile.ZipFile(input_f)
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
    input_f.seek(0)

  elif outer_ext not in ALLOWED_EXTENSIONS:
    # If it's not .wwz, it must be a text file.  This doesn't respect
    # check_wwz_names.
    raise RuntimeError('File %r has an invalid extension' % form_val.filename)

  out_path = os.path.join(out_dir, form_val.filename)

  # Note: this check may be racy, but it protects against some accidents
  allow_overwrite = policy.get('allow_overwrite', False)
  if not allow_overwrite and os.path.exists(out_path):
    raise RuntimeError('File already exists: %r' % out_path)

  # The PID is unique at a given point in time.  The worst case is that a
  # script is interrupted and the file is left there.
  tmp_out_path = '%s.wwup-%d' % (out_path, os.getpid())

  CopyFile(input_f, tmp_out_path)

  # Make it read-only, just in case.  It still can be replaced by os.rename() or mv.
  os.chmod(tmp_out_path, 0o444)
  os.rename(tmp_out_path, out_path)

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


def GetFileValues(form):
  # FieldStorage only supports 'in'
  # - it doesn't support .get()
  # - getvalue() gives a string

  pairs = []
  for k in ['file1', 'file2', 'file3']:
    if k not in form:
      break
    pairs.append((k, form[k]))
  return pairs


def Upload(environ, form, dest_base_dir):

  # Form field examples:
  #   payload-type=osh-runtime
  #   subdir=git-1ab435d
  #   file1=@foo.wwz

  if 'payload-type' not in form:
    raise RuntimeError('Expected payload type')
  payload_type = form['payload-type'].value

  policy = PAYLOADS.get(payload_type)
  if policy is None:
    raise RuntimeError('Invalid payload type %r' % payload_type)

  num_bytes = int(environ['CONTENT_LENGTH'])
  # Low limit of 10_000 by default
  max_bytes = policy.get('max_bytes', 10000)
  if num_bytes > max_bytes:
      raise RuntimeError('POST body is %s bytes, but only %s are allowed' %
          (num_bytes, max_bytes))

  if 'subdir' not in form:
    raise RuntimeError('Expected subdir')
  subdir = form['subdir'].value

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

  file_vals = GetFileValues(form)
  for param_name, file_val in file_vals:
    summaries.append(DoOneFile(param_name, policy, environ, file_val, out_dir))

  PrintStatusOk()

  print('--- wwup.cgi Upload ---')
  print('')
  print('payload type = %s' % payload_type)
  print('subdir = %r' % subdir)
  print('num bytes = %r' % num_bytes)
  print('')

  for summary in summaries:
    print('summary = %r' % summary)
  print('')


def GetMoreArgv(form):
  argv = []
  for k in ['arg1', 'arg2', 'arg3']:
    if k not in form:
      break
    # TODO: assert that it's a string, not a value?
    argv.append(form[k].value)
  return argv


def RunHook(environ, home_dir, hook_config, form):
  argv0 = hook_config['argv0']
  assert not os.path.isabs(argv0), argv0

  argv0_path = os.path.join(home_dir, argv0)
  argv_prefix = hook_config.get('argv_prefix', [])

  argv = [argv0_path] + argv_prefix + GetMoreArgv(form)

  p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  stdout, stderr = p.communicate()

  status = p.wait()
  if status == 0:
    PrintStatusOk()
  else:
    PrintError500()

  print('--- wwup.cgi run-hook ---')
  print('hook %r' % hook_config)
  print('argv %r' % argv)
  print('')

  print('')
  print('--- STATUS: %d' % status)
  print('')

  print('--- STDOUT:')
  print('')
  print(stdout)
  print('')
  print('')

  print('--- STDERR:')
  print('')
  print(stderr)
  print('')
  print('')


def GetHomeDir():
    uid = os.getuid()
    try:
        e = pwd.getpwuid(uid)
    except KeyError:
        raise AssertionError("Couldn't get home dir")

    return e.pw_dir


def main(argv):
  if 1:
    cgitb.enable()  # Enable tracebacks
  else:
    # Dumps to file
    cgitb.enable(display=0, logdir='/home/oils', format='text')

  method = os.getenv('REQUEST_METHOD', 'GET')

  if method == 'GET':
    print(r'''
wwup.cgi - HTTP uploader

Example usage:

    curl \
      --form 'payload-type=osh-runtime' \
      --form 'subdir=git-123' \
      --form 'file1=@myfile.wwz' \
      $URL

    curl \
      --form 'payload-type=github-jobs' \
      --form 'subdir=1234' \
      --form 'file1=@benchmarks.wwz' \
      --form 'file2=@benchmarks.tsv' \
      --form 'file3=@benchmarks.json' \
      $URL

    curl \
      --form 'run-hook=soil-event-job-done' \
      --form 'arg1=foo' \
      --form 'arg2=bar' \
      $URL
''')
    return

  # Dumps info
  #cgi.test()

  # TODO: We could throttle here, e.g. if there are too many files

  dest_base_dir = sys.argv[1]

  form = cgi.FieldStorage(fp=sys.stdin, environ=os.environ)

  try:
    if 'cgitb-test' in form:
      # BUG
      print(sys.argv[99])

    elif 'run-hook' in form:
      run_hook = form['run-hook'].value
      home_dir = GetHomeDir()
      hook_config = HOOKS.get(run_hook)
      if hook_config is None:
        raise RuntimeError('Invalid hook %r' % run_hook)
      RunHook(os.environ, home_dir, hook_config, form)
    else:
      Upload(os.environ, form, dest_base_dir)
  except RuntimeError as e:
    PrintError400()
    print('Status: 400 Bad Request')
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

  print('--- wwup.cgi Done ---')


if __name__ == '__main__':
  main(sys.argv)

# vim: sw=2
