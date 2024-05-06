#!/usr/bin/env python2
from __future__ import print_function
"""
wwup.cgi

Upload untrusted user content.

- Validate the uploaded data
  - Only data files like .txt .tsv .csv .json are allowed.
  - No web content like .html .css .js.
  - Maybe enforce naming?

- Control resource usage
  - Limit the size of each upload
  - Delete old files automatically
  - Check total size and space perhaps?

- Run aggregation hooks
  - Concatenate TSV files for easier analysis
  - Generate HTML with trusted binaries
"""

import cgi
import cgitb
import cStringIO
import os

# To validate files inside .wwz
# (We could also extract zip payloads)
import zipfile

# Hard-coded payload validation:

# definitely no .js .css .html
ALLOWED_EXTENSIONS = ['.txt', '.tsv', '.csv', '.json']

# Additional rule: you can never overwrite a file!  You can only create new
# files.


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

  'really-small': {
    'max_files': 2,
    'max_bytes': 1000,
  },

  # Is this one policy, or multiple policies?
  'oils-ci': {
  }
}


#cgi.test()

def Upload():
  form = cgi.FieldStorage()

  # Form fields
  # - payload-type=osh-runtime
  # - zip=foo.zip  # files to extract

  payload_type = form.getfirst('payload-type')
  if payload_type is None:
      raise RuntimeError('Expected payload type')

  policy = PAYLOADS.get(payload_type)
  if policy is None:
      raise RuntimeError('Invalid payload type %r' % payload_type)

  wwz_contents = form.getfirst('wwz')
  if wwz_contents is None:
      raise RuntimeError('Expected wwz')

  f = cStringIO.StringIO(wwz_contents)
  try:
    z = zipfile.ZipFile(f)
  except zipfile.BadZipfile as e:
    raise RuntimeError('Error opening zip: %s' % e)

  names = z.namelist()
  num_files = len(names)

  max_files = policy['max_files']
  if num_files > max_files:
      raise RuntimeError('wwz has %d files, but only %d are allowed' %
          (num_files, max_files))

  for rel_path in names:
    _, ext = os.path.splitext(rel_path)
    if ext not in ALLOWED_EXTENSIONS:
      raise RuntimeError('File %r has an invalid extension' % rel_path)

  print('Status: 200 OK')
  print('Content-Type: text/plain; charset=utf-8')
  print('')
  print('Hi from wwup.cgi')

  print('t %r' % payload_type)
  print('z %d' % len(wwz_contents))

  print('%d files in wwz' % len(names))
  for rel_path in names:
    print('%r' % rel_path)


def main():
  cgitb.enable()  # Enable tracebacks

  # TODO:
  # - The root upload dir could be an argument, rather than relying on CWD
  # - We check here that there are not too many files

  try:
    Upload()
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

  print('DONE')


if __name__ == '__main__':
  main()
