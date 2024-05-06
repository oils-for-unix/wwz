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

    CASES = [
        (['file.txt', 'dir/file.txt'], ''),
        # list inside
        (['file.txt', 'dir/file.txt'], 'dir/'),

        (['file.txt', 'dir/empty-dir/'], ''),
        (['file.txt', 'dir/sub1/z', 'dir/sub1/x', 'dir/sub2/'], 'dir/'),
        ]

    for rel_paths, dir_prefix in CASES:
      page_data = {'files': [], 'dirs': []}
      wwz._MakeListing(page_data, rel_paths, dir_prefix)
      print(pformat(page_data, indent=2))


if __name__ == '__main__':
  unittest.main()
