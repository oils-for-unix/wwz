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

  def testValidate(self):

    CASES = ['', '.', '../..', 'subdir/..']
    for s in CASES:
      error_msg = wwup.ValidateSubdir(s, 2)
      self.assert_(error_msg is not None)
      print('%r %r' % (s, error_msg))

    CASES2 = [
        ('foo', 2),
        ('foo/bar/baz', 2),
        ]
    for s, expected_depth in CASES2:
      error_msg = wwup.ValidateSubdir(s, expected_depth)
      self.assert_(error_msg is not None)
      print('%r %r' % (s, error_msg))

    self.assertEqual(None, wwup.ValidateSubdir('one', 1))
    self.assertEqual(None, wwup.ValidateSubdir('one/two', 2))
    self.assertEqual(None, wwup.ValidateSubdir('one/two/three', 3))


if __name__ == '__main__':
  unittest.main()

# vim: sw=2

