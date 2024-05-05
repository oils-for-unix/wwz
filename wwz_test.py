#!/usr/bin/env python2
"""
wwz_test.py: Tests for wwz.py
"""
from __future__ import print_function

from pprint import pformat
import unittest

import wwz  # module under test


class WwzTest(unittest.TestCase):
  def setUp(self):
    pass

  def tearDown(self):
    pass

  def testMakeListing(self):
    print(wwz)

    rel_paths = ['file.txt', 'dir/file.txt']
    p = wwz._MakeListing('foo.wwz', rel_paths, '')
    print(pformat(p, indent=2))

    rel_paths = ['file.txt', 'dir/file.txt']
    p = wwz._MakeListing('foo.wwz', rel_paths, 'dir/')
    print(pformat(p, indent=2))

    rel_paths = ['file.txt', 'dir/empty-dir']
    p = wwz._MakeListing('foo.wwz', rel_paths, '')
    print(pformat(p, indent=2))

    rel_paths = ['file.txt', 'dir/sub1/z', 'dir/sub1/x', 'dir/sub2/']
    p = wwz._MakeListing('foo.wwz', rel_paths, 'dir/')
    print(pformat(p, indent=2))


if __name__ == '__main__':
  unittest.main()
