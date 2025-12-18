cgit setup
==========

See `cgit/run.sh`

- build time config: `cgit.conf` is a makefile fragment
- runtime config
  - `cgitrc`
  - .htaccess
    - allow CGI 
    - TODO: rewrite URLs
  - robots.txt: the one provided disallows snapshots
