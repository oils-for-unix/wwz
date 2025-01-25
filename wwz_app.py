#!/usr/bin/env python2

# Meant to be imported by Gunicorn

import os

import wwz

request_log = wwz.NoLogFile()
trace_log = wwz.NoLogFile()

log_dir = '/home/oils/wwz-logs-gunicorn'

app = wwz.App(request_log, trace_log, log_dir, os.getpid())
