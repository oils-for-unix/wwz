wwz
===

A FastCGI program that serves files from a zip file.  See this comment for
context:

- <https://lobste.rs/s/xl63ah/fastcgi_forgotten_treasure#c_4jggfz>
- Related answer: Why FastCGI and not HTTP?  Because FastCGI processes are
  stateless/ephemeral.
  - <https://lobste.rs/s/xl63ah/fastcgi_forgotten_treasure#c_kaajpp>
- Why FastCGI and not CGI?  For lower latency.  We "cache" the opening of the
  zip file, and the overhead of starting CPython.

## The General Idea

`wwz.py` is a very small WSGI app.  You download the `flup` "middleware" which
turns the WSGI app into a FastCGI server.  (Analogously, you can turn a WSGI
app into a CGI program.)

## Files

    wwz.py         # The WSGI program
    wwz-test.sh    # Shell tests for the FastCGI program
    wwz.htaccess   # A snippet to configure Apache on Dreamhost
    admin.sh       # Some shell functions that may be useful

Not included:

    dispatch.fcgi  # A shell wrapper specific to the hosting environment.

## Local Development

I do this both locally **and** on the server:

    ./admin.sh download-flup  # Yes this is old but it works!
    ./admin.sh build-flup
    ./admin.sh smoke-test

Then test out the app locally:

    ./wwz-test.sh make-testdata  # makes a zip file
    ./wwz-test.sh all

## Deploying

I deploy it on Dreamhost.  Instructions vary depending on the web host.  (TODO:
I want to stand it up on NearlyFreeSpeech too.)

Requirements:

1. A directory for the binary
2. A directory for logs and unhandled exceptions.
3. A `dispatch.fcgi` script that sets PYTHONPATH and execs `wwz.py`.
4. The `.htaccess` file for Apache to read.

If all those elements are in place, Dreamhost's Apache server will send
requests like 

    https://www.oilshell.org/release/0.8.1/test/wild.wwz/

to a `wwz.py` process that the `dispatch.fcgi` shell wrapper started.  (The web
host maintains a FastCGI process manager, so a process isn't started on every
request.)

Example deploy function:

    for-travis() {
      local dest=~/travis-ci.oilshell.org

      mkdir -v -p $dest/wwz-bin ~/wwz-logs

      cp -v wwz.htaccess $dest/.htaccess

      cp -v wwz.py $dest/wwz-bin/
      cp -v travis_dispatch.fcgi $dest/wwz-bin/dispatch.fcgi

      make-testdata
      copy-testdata
    }

Example `dispatch.fcgi`:

    #!/bin/sh
    root=/home/travis_admin/git/dreamhost/wwz-fastcgi

    PYTHONPATH=$root/_tmp/flup-1.0.3.dev-20110405 \
      exec ~/travis-ci.oilshell.org/wwz-bin/wwz.py ~/wwz-logs

You can also set `WWZ_REQUEST_LOG=1` and/or `WWZ_TRACE_LOG=1` to get more
detailed logs.

## Administering

Sometimes I do this on the server:

    ./admin.sh kill-wwz




