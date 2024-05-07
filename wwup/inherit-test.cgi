#!/usr/bin/env python2
from __future__ import print_function

import os
import cgi
import cgitb
import sys

if 1:
  print('Status: 200 OK')
  print('Content-Type: text/plain; charset=utf-8')
  print('')
  print('BEFORE MAIN')

class MyFieldStorage(cgi.FieldStorage):
  """To atomically rename the temp file to a real file.

  We make it read-only, so it can't be overwritten.
  """
  #def __init__(self, tmp_dir, fp, environ):
  #  cgi.FieldStorage.__init__(self, fp=fp, environ=environ)

  def __init__(self, tmp_dir, *args, **kwargs):
    print('args %s' % (args,))
    print('kwargs %s' % kwargs)
    cgi.FieldStorage.__init__(self, *args, **kwargs)
    self.tmp_dir = tmp_dir
  #def __init__(self, *args, **kwargs):
  #  cgi.FieldStorage.__init__(self, *args, **kwargs)

  #def ZZ_make_file(self, binary=None):
  #  self.tmp_fd, self.tmp_path = tempfile.mkstemp(prefix='wwup-',
  #      dir=self.tmp_dir)

def main():
  cgitb.enable()

  if 0:
    cgi.test()
    return

  if 0:
    print('Status: 200 OK')
    print('Content-Type: text/plain; charset=utf-8')
    print('')
    print('OK')
    return

  if 1:
    #form = cgi.FieldStorage(fp=sys.stdin, environ=os.environ)

    tmp_dir = '/tmp'
    if 0:
      form = MyFieldStorage(fp=sys.stdin, environ=os.environ)
      # WTF, this works
      form.tmp_dir = tmp_dir

    form = MyFieldStorage(tmp_dir, fp=sys.stdin, environ=os.environ)

    print('Status: 200 OK')
    print('Content-Type: text/plain; charset=utf-8')
    print('')
    print('foo = %r' % form.getvalue('foo'))

  #return


main()

