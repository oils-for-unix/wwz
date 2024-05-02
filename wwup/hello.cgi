#!/usr/bin/env bash

# No HTTP status in CGI

echo 'Content-Type: text/html; charset=utf-8'
echo

# Test UTF-8
echo $'<a href="/">Hello \u03bc</a>'
