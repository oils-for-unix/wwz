#!/usr/bin/env python2

# No HTTP status in CGI

print 'Content-Type: text/html; charset=utf-8'
print

# Test UTF-8
print u'<a href="/">Hello \u03bc</a>'.encode('utf-8')
