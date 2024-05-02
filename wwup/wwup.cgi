#!/usr/bin/env python2
from __future__ import print_function

import cgi

# for extracting any zip files
# files with .wwz extension are not extracted?
import zipfile

#cgi.test()

def main():
  form = cgi.FieldStorage()
  print('Content-Type: text/plain; charset=utf-8')
  print('')

  print(form)

  print()
  print(form['files[]'])
  print()
  print(form['files2'])
  print()


  from pprint import pprint

  print('LIST')
  print()
  pprint(form.getlist('files[]'), indent=4)
  print()
  pprint(form.getlist('files2'), indent=4)


main()
