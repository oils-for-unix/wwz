wwup
====

Simple HTTP file uploader in Python, as a CGI program.

Why?

- HTTP uploads generally need to be MIME / form encoded, e.g. what curl --form does
  - Dreamhost's Apache modsecurity actually blocks many requests that look
    "weird".  They scan the HTTP request headers and body.
- Shell scripts can't parse MIME bodies correctly
- The Python 2 cgi module has this built in
  - I don't think wsgiref has it.  I remember doing a hack many years ago to
    connect wsgiref and cgi.
- Unlike wwz, we don't need FastCGI for uploads.  We actually want a separate
  process per upload.
- PHP has a built-in parser and `$_FILES`, but I already used it for hashdiv
  - wwz is written in Python, so let's stick with Python


## TODO

- be mindful of race conditions writing files
  - can we overwrite files, or only create new ones?



## Notes

- hello.cgi has a bash shebang line, but Dreamhost runs it with /bin/sh
  instead!
  - Probably left over from ShellShock.



