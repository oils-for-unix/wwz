#!/usr/bin/env python2
"""
wwup_test.py: Tests for wwup.py
"""
from __future__ import print_function

import cStringIO
import unittest

import wwup  # module under test


class FooTest(unittest.TestCase):
  def setUp(self):
    pass

  def tearDown(self):
    pass

  def testFoo(self):
    print(wwup)
    f = cStringIO.StringIO('')
    form = wwup.MyFieldStorage('/tmp', f, {})

    x = form.getfirst('x')
    print(x)


if __name__ == '__main__':
  unittest.main()
