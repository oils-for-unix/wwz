#!/usr/bin/python -S
"""
wwz.py

-S gives a slight speedup. Although most of the latency appears to be on the
Dreamhost side.

TODO:
  - Investigate caching headers.  What does Dreamhost do for dynamic content?
    We want it to behave like static content.

- Problem: should we serve .js and .css with content types?
  - The problem is that they will be slow.  Maybe best to keep them outside.

Example request:

Given the rewrite rule in .htaccess, and URL
http://chubot.org/wwz-test/foo.wwz/a/b/c 

we get CGI vars:

PATH_INFO = /a/b/c
REQUEST_URI = /wwz-test/foo.wwz/a/b/c
DOCUMENT_ROOT = /home/chubot/chubot.org
"""

import cgi
import os
import sys
import time
import threading
import traceback
from email.utils import formatdate  # for HTTP header
# NOTE: this is not the full 'zipfile' module (in Python), but it has the
# functionality we need (in C).  We only want to extract zip files, and this is
# faster.
import zipimport 
# Performance note: with 40K files in a 61 MB zip file, this is even slower
# than zipimport!  ~700 ms vs. ~450 ms.
#
# import zipfile
# with zipfile.ZipFile(wwz_path) as z:
#   body = z.read(internal_path)


from flup.server.fcgi import WSGIServer
# OLD MODULE.  I tested this and it has the same 1.0 delay, which might be
# cilent DNS or Dreamhost.
#from fcgi import WSGIServer


# To find out if a zip file is cached, you have to join request log and.

# Will this show up in apache logs?  Or is that generated by mod_fcgi?
# UNIQUE_ID Wf-SE0Wj2GQAADYR0E8AAAAF

# TODO: unique_id to join with access.log.
# PID is in the (pid, request_counter) can be used to join request.log and
# trace.log.

# timestamp: should it have a unix-timestamp type?  automatically seconds in float?
# then it can automatically be printed
# request_counter: int
# everything else is string

REQUEST_LOG_SCHEMA = [
    ('unique_id', 'string'),
    ('request_counter', 'integer'),
    ('thread_name', 'string'),
    ('timestamp', 'double'),
    ('request_uri', 'string'),
]

TRACE_SCHEMA = [
    ('unique_id', 'string'),
    ('request_counter', 'integer'),
    ('event_name', 'string'),
    ('timestamp', 'double'),
]


class LogFile(object):
  """Interface that the app uses."""

  def Append(self, row):
    pass

  def Flush(self):
    pass


class NoLogFile(LogFile):
  pass

# No locking because we assume that records are less than 4096 bytes, and those are atomic:
# http://www.notthewizard.com/2014/06/17/are-files-appends-really-atomic/

class TabularLogFile(LogFile):
  """
  Manages:
  - schema (data integrity)
  - file flushing policy
  - encoding (TSV)
  """
  def __init__(self, schema, path):
    self.f = open(path, 'w')  # not append
    header = [name for name, _ in schema]

    # TODO: Write .schema.csv?
    self.f.write('\t'.join(header))
    self.f.write('\n')

  def Append(self, row):
    self.f.write('\t'.join(str(cell) for cell in row))
    self.f.write('\n')

  def Flush(self):
    self.f.flush()


class RequestTracer(object):

  def __init__(self):
    self.events = []
    self.start_time = time.time()

  def Event(self, msg):
    """Record a timestamp and string."""
    ts = time.time() - self.start_time
    self.events.append((ts * 1000, msg))  # milliseconds

  def GetEvents(self):
    return self.events


def log(msg, *args):
  """Print to stderr.  Shows up in error.log."""
  if args:
    msg = msg % args
  print >>sys.stderr, msg


def NotFound(start_response, msg, *args):
  """
  Usage: yield NotFound(...)
  """
  if args:
    msg = msg % args
  start_response('404 Not Found', [('Content-Type', 'text/html; charset=utf-8')])
  return """\
<h1>404 Not Found</h1>
<p>%s</p>
""" % cgi.escape(msg)


DEBUG = False
#DEBUG = True


class App(object):
  def __init__(self, request_log, trace_log, log_dir, pid):
    self.traces = []

    self.request_log = request_log
    self.trace_log = trace_log
    self.log_dir = log_dir

    # path -> zipimporter instance.  They are assumed to be immutable.  If you
    # mutate one, you have to restart the FastCGI process.

    # TODO: Need to lock this
    self.zip_files = {}
    self.zip_files_lock = threading.Lock()  # multiple threads may access state

    # for monitoring
    self.pid = pid
    self.request_counter = 0

  def StatusPage(self, environ, start_response):
    """Serve the status page so we can monitor it.

    TODO: Should we just have a JSON page and an HTML page?
    Or only JSON?

    """
    start_response('200 OK', [('Content-Type', 'text/html; charset=utf-8')])
    yield """
<!DOCTYPE html>
<html>
  <head>
    <title>wwz Status</title>
  </head>
  <body>
"""

    yield '<h3>wwz Status</h3>\n'

    yield '<p>PID = %d</p>' % self.pid

    # By default, I'm seeing a thread pool of 5.  Does more concurrency help?
    th = threading.current_thread()
    yield '<p>thread ID = %d</p>' % th.ident
    yield '<p>thread name = %s</p>' % cgi.escape(th.getName())

    yield '<p>current time = %s</p>' % time.time()
    yield '<p>num requests = %d</p>' % self.request_counter

    yield '<h3>zip files open</h3>'
    for name in self.zip_files:  # is this thread safe?
      yield '<p>%s</p>' % cgi.escape(name)

    yield '<h3>traces</h3>'
    for trace in self.traces:  # is this thread safe?
      yield '<p><pre>'
      for ts, event in trace:  # ts is in milliseconds
        yield '%.2f %s\n' % (ts, cgi.escape(event))
      yield '</pre></p>'

    yield '<h3>FastCGI Environment</h3>'

    yield '<table>'
    for k, v in sorted(environ.items()):
        yield '<tr><td>%s</td><td><code>%s</code></td></tr>\n' % (cgi.escape(str(k)), cgi.escape(str(v)))
    yield '</table>'
    yield """
    <hr/>
  </body>
</html>
"""

  def _LogException(self, unique_id, request_uri, exc_type, e, tb):
    # For now, create a file for each exception.  Use a simple name and a
    # simple format.  Eventually it might be nice to revive my simple UDP
    # server.
    out_path = os.path.join(self.log_dir, 'exception.%s.txt' % time.time())
    with open(out_path, 'w') as f:
      f.write(unique_id)
      f.write('\n')
      f.write(request_uri)
      f.write('\n')

      f.write('---\n')
      f.write(str(exc_type))
      f.write('\n')

      f.write('---\n')
      f.write(str(e))
      f.write('\n')

      f.write('---\n')
      traceback.print_tb(tb, None, f)  # no limit
      f.write('\n')

  def __call__(self, environ, start_response):
    """Wrap the real request in tracing."""

    unique_id = environ.get('UNIQUE_ID', '-')  # from mod_unique_id, for joining logs
    request_uri = environ.get('REQUEST_URI', '-')

    try:
      tracer = RequestTracer()

      self.request_counter += 1
      request_counter = self.request_counter  # copy it into this thread for later

      th = threading.current_thread()  # new thread for every request
      entry = (unique_id, request_counter, th.getName(), time.time(), request_uri)
      self.request_log.Append(entry)

      try:
        for chunk in self.Respond(environ, start_response, tracer):
          yield chunk
      finally:
        # Make sure we don't lose any requests, since there are early returns.

        # Flush to disk afterward.
        for ts, name in tracer.GetEvents():
          entry = (unique_id, request_counter, ts, name)
          self.trace_log.Append(entry)
        self.trace_log.Flush()
        self.request_log.Flush()
    except Exception:
      exc_type, e, tb = sys.exc_info()
      self._LogException(unique_id, request_uri, exc_type, e, tb)
      # NOTE: The WSGI server will catch this.  But it might be better to let
      # it restart!  That will clear the error that happens when the zip file
      # is updated.
      # I think I have to patch flup then.
      raise

  def Respond(self, environ, start_response, tracer):
    """Called from multiple threads."""
    request_uri = environ['REQUEST_URI']
    path_info = environ.get('PATH_INFO', '')

    # PATH_INFO may be unset if you visit http://example.com/cgi-bin/wwz.py with
    # no trailng path.
    if not path_info:
      for chunk in self.StatusPage(environ, start_response):
        yield chunk
      tracer.Event('StatusPage-end')
      return

    doc_root = environ['DOCUMENT_ROOT']

    if DEBUG:
      log('REQUEST_URI = %r', request_uri)

      log('PATH_INFO = %r', path_info)
      log('DOCUMENT_ROOT = %r', doc_root)

    n = len(path_info)
    wwz_rel_path = request_uri[1:-n]  # remove leading /

    wwz_path = os.path.join(doc_root, wwz_rel_path)

    internal_path = path_info[1:]  # remove leading /
    # The zipimporter has directory entries.  But we don't want to serve empty
    # files!
    if internal_path == '' or internal_path.endswith('/'):
      internal_path += 'index.html'

    tracer.Event('zip-begin')

    # NOTE: We are doing coarse-grained locking here.  Technically, we could
    # try not to lock when reading the zip file, but it's more complex.  We
    # don't know if two cold hits in a row go to the same zip file.  We don't
    # want to concurrent create duplicate objects.
    with self.zip_files_lock: 
      try:
        z = self.zip_files[wwz_path]
      except KeyError:
        tracer.Event('open-zip')
        try:
          z = zipimport.zipimporter(wwz_path)
        except zipimport.ZipImportError as e:
          yield NotFound(start_response, "Couldn't open wwz path %r", wwz_path)
          return
        self.zip_files[wwz_path] = z
        tracer.Event('cached-zip')

    tracer.Event('zip-end')

    is_binary = False
    if internal_path.endswith('.html'):
      content_type = 'text/html'
    elif internal_path.endswith('.css'):
      content_type = 'text/css'
    elif internal_path.endswith('.js'):
      content_type = 'application/javascript'
    elif internal_path.endswith('.json'):
      content_type = 'application/json'
    elif internal_path.endswith('.png'):
      content_type = 'image/png'
      is_binary = True
    elif internal_path.endswith('.tar'):  # for _release/oil.tar
      # https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types
      content_type = 'application/x-tar'
      is_binary = True
    else:
      content_type = 'text/plain'  # default

    try:
      body = z.get_data(internal_path)
    except IOError as e:
      yield NotFound(start_response, 'Path %r not found in wwz archive', internal_path)
      return

    tracer.Event('data-read')

    # Use the timestamp on the whole .zip file as the Last-Modified header.  If
    # ANY file in the .zip is modified, consider the whole thing modified.  I
    # think that is fine.
    mtime = os.path.getmtime(wwz_path)

    headers = []
    if not is_binary:
      content_type = '%s; charset=utf-8' % content_type

    headers = [
        ('Content-Type', content_type),
        # https://stackoverflow.com/questions/225086/rfc-1123-date-representation-in-python
        ('Last-Modified', formatdate(mtime, localtime=False, usegmt=True)),
    ]

    # Dreamhost does send ETag.
    # Semi-unique hash gets perserved.  TODO: Bake an md5sum into .zip metadata?
    # Does this make the browser send conditional GETs?  Do crwalers ever use
    # this?
    #print 'ETag: %s' % hash(internal_path)

    start_response('200 OK', headers)
    yield body

    tracer.Event('request-end')


def main(argv):
  log_dir = argv[1]  # for exceptions

  pid = os.getpid()
  timestamp = time.strftime('%Y-%m-%d__%H-%M-%S')

  log_requests = os.getenv('WWZ_REQUEST_LOG')
  if log_requests:
    path1 = os.path.join(log_dir, '%s.%d.request.log' % (timestamp, pid))
    request_log = TabularLogFile(REQUEST_LOG_SCHEMA, path1)
  else:
    request_log = NoLogFile()

  trace = os.getenv('WWZ_TRACE_LOG')
  if trace:
    path2 = os.path.join(log_dir, '%s.%d.trace.log' % (timestamp, pid))
    trace_log = TabularLogFile(TRACE_SCHEMA, path2)
  else:
    trace_log = NoLogFile()

  # Global instance shared by all threads.
  app = App(request_log, trace_log, log_dir, pid)

  # NOTE: debug=True shows tracebacks.
  WSGIServer(app, debug=True).run()
  #WSGIServer(app).run()


if __name__ == '__main__':
  main(sys.argv)
