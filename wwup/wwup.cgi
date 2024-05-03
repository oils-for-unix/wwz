#!/usr/bin/env python2
from __future__ import print_function

import cgi

# for extracting any zip files
# files with .wwz extension are not extracted?
import zipfile


# Hard-coded payload validation:

# definitely no .js .css .html
ALLOWED_EXTENSIONS = ['.txt', '.tsv', '.csv', '.json']

# Additional rule: you can never overwrite a file!  You can only create new
# files.


# Rules by payload:

PAYLOAD_GLOBS = {
  'osh-runtime': {
    'globs': [
      'osh-runtime/*.tsv',  # times, provenance, gc-stats
      'shell-id/*-*/*.txt',
      'host-id/*-*/*.txt',
    ],
    'max_files': 20,
    'max_bytes': 10 * 1000 * 1000,  # 10 MB
  }
}


#cgi.test()

def Upload():
  form = cgi.FieldStorage()

  print('Content-Type: text/plain; charset=utf-8')
  print('')
  print('OK')

  # Form fields
  # - payload-type=osh-runtime
  # - zip=foo.zip  # files to extract

  payload_type = form.getfirst('payload-type')
  if payload_type is None:
      raise RuntimeError('Expected payload type')
  if payload_type not in PAYLOAD_GLOBS:
      raise RuntimeError('Invalid payload type %r' % payload_type)

  zip_contents = form.getfirst('zip')
  if zip_contents is None:
      raise RuntimeError('Expected zip')

  print('t %r' % t)
  print('z %r' % z)


def main():

  try:
    Upload()
  except RuntimeError as e:
    # CGI has a Status: header!
    print('Status: 400 Bad Request')
    print('Content-Type: text/plain; charset=utf-8')
    print('')
    print('Bad request: %s' % e)


main()
