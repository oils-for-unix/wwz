#!/usr/bin/env python2
"""
wwup_test.py: Tests for wwup.py
"""
from __future__ import print_function

import cStringIO
import unittest

import wwup  # module under test


class WwupTest(unittest.TestCase):

  def testRunHook(self):
    home_dir = wwup.GetHomeDir()
    hook_config = wwup.HOOKS.get('local-test')
    wwup.RunHook({}, home_dir, hook_config, {})

  def testAtomicRename(self):
    import os

    # Making these read only does not prevent them from being REPLACED.
    # I guess you have to protect the DIRECTORY itself.  Do that later.

    return

    os.system('echo foo > _tmp/foo; chmod 444 _tmp/foo')
    os.system('echo bar > _tmp/bar; chmod 444 _tmp/bar')

    os.rename('_tmp/foo', '_tmp/final')
    os.rename('_tmp/bar', '_tmp/final')

    os.system('cat _tmp/final')

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

