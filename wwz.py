#!/usr/bin/env python2
from __future__ import print_function
"""
wwz.py - Serve web content directly from a zip file.

-S gives a slight speedup. Although most of the latency appears to be on the
Dreamhost side.
"""

import cgi
import os
import re
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
# with zipfile.ZipFile(wwz_abs_path) as z:
#   body = z.read(rel_path)


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
  print(msg, file=sys.stderr)


HTML_UTF8 = ('Content-Type', 'text/html; charset=utf-8')


def _HtmlHeader(title, css_url):
  return """
<!DOCTYPE html>
<html>
  <head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>%s</title>
    <link rel="stylesheet" type="text/css" href="%s" />
  </head>
  <body>
""" % (cgi.escape(title), cgi.escape(css_url))


def _HtmlFooter():
  return """
  </body>
</html>
"""



def Ok(start_response, headers, body):
  start_response('200 OK', headers)
  return [body]


def BadRequest(start_response, msg, *args):
  """
  Usage: return BadRequest(start_response, 'message %r', arg)
  """
  if args:
    msg = msg % args
  start_response('400 Bad Request', [HTML_UTF8])
  body = """\
<h1>wwz: 400 Bad Request</h1>
<p>%s</p>
""" % cgi.escape(msg)
  return [body]


def NotFound(start_response, msg, *args):
  """
  Usage: return NotFound(start_response, 'message %r', arg)
  """
  if args:
    msg = msg % args
  start_response('404 Not Found', [HTML_UTF8])
  body = """\
<h1>wwz: 404 Not Found</h1>
<p>%s</p>
""" % cgi.escape(msg)
  return [body]


# Don't print unsanitized request path to header, which would allow header
# injection.
# flup doesn't appear to take care of this!
#
# Be conservative.

REDIRECT_RE = re.compile(r'^[a-zA-Z0-9_./-]*$')

def Redirect(start_response, location):
  """
  Usage: return Redirect(start_response, 'http://example.com')
  """
  start_response('302 Found', [HTML_UTF8, ('Location', location)])
  body = """\
<h1>wwz: 302 Found</h1>
<p>%s</p>
""" % cgi.escape(location)
  return [body]


DEBUG = False
#DEBUG = True


def _MakeListing(page_data, rel_paths, dir_prefix):

  dirs = set()
  files = []

  assert dir_prefix == '' or dir_prefix.endswith('/'), dir_prefix

  for rel_path in rel_paths:
    if rel_path == dir_prefix:
      continue  # don't list yourself
    if not rel_path.startswith(dir_prefix):
      continue  # not under this dir

    if rel_path == dir_prefix + 'index.html':
      page_data['index_html'] = True

    zip_rel_path = rel_path[len(dir_prefix):]

    # Here we assume that dirs end with /, but files don't.
    # That appears to be true in zips.

    slash1 = zip_rel_path.find('/')
    if slash1 == -1:
      # foo -> file is foo
      files.append(zip_rel_path)
    else:
      # Note: we can have a rel_path _tmp/soil/, but NOT _tmp/
      dir_name = zip_rel_path[:slash1+1]  # include /
      dirs.add(dir_name)

  page_data['files'].extend(sorted(files))
  page_data['dirs'].extend(sorted(dirs))


def _MakeCrumb2(crumb2, wwz_name, dir_prefix):

  parts = [p for p in dir_prefix.split('/') if p]
  anchors = [wwz_name] + parts

  urls = [None] * len(anchors)
  n_inside = len(anchors)
  for i in xrange(n_inside - 1):
    dots = ['..'] * (n_inside - i - 1)
    urls[i] = '/'.join(dots) + '/-wwz-index'

  crumb2['anchors'] = anchors
  crumb2['urls'] = urls

  return n_inside


def _MakeCrumb1(crumb1, n_inside, http_host, wwz_base_url):

  #
  # Now go even further back
  #

  parts = [p for p in wwz_base_url.split('/') if p]
  parts.pop()  # remove .wwz 

  anchors = [http_host] + parts

  urls = [None] * len(anchors)
  n_before = len(anchors)
  for i in xrange(n_before):
    dots = ['..'] * (n_inside + n_before - i - 1)
    urls[i] = '/'.join(dots) + '/'  # use web server index

  crumb1['anchors'] = anchors
  crumb1['urls'] = urls


def _Breadcrumb(crumb, last_slash=False):
  yield '<div class="breadcrumb">\n'
  i = 0
  for anchor, link in zip(crumb['anchors'], crumb['urls']):
    if i != 0:
      yield '/\n'  # separator

    if link is None:
      yield '<span>%s</span>\n' % cgi.escape(anchor)
    else:
      yield '<a href="%s">%s</a>\n' % (cgi.escape(link, quote=True),
                                       cgi.escape(anchor))
    i += 1

  if last_slash:
    yield '/\n'

  yield '</div>\n\n'


def _EntriesHtml(heading, entries, url_suffix=''):
  yield '<h1>%s</h1>\n' % cgi.escape(heading)

  if len(entries):
    for entry in entries:
      escaped = cgi.escape(entry, quote=True)
      yield '<a href="%s">%s</a> <br/>\n' % (escaped + url_suffix, escaped)
  else:
    yield '<p><i>(no entries)</i></p>\n'

  yield '\n'


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

    Note: we could also have a JSON status page
    """
    start_response('200 OK', [HTML_UTF8])
    title = 'Status of wwz process %d' % self.pid
    yield _HtmlHeader(title, '-wwz-css')

    yield '''
    <div style="text-align: right">
      <a href="..">Up</a> | <a href="%s">wwz Index</a>
    </div>
    ''' % '-wwz-index'

    yield '<h1>%s</h1>\n' % title

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
    yield '<hr/>\n'
    yield _HtmlFooter()

  def IndexListing(self, start_response, http_host, wwz_base_url, wwz_abs_path,
                   rel_path, dir_prefix, last_modified):
    """
    wwz_base_url: /dir/foo.wwz
    wwz_abspath: /home/andy/dir/foo.wwz
    """
    # 2024-05: Use zipfile module, not zipimport, because it can list files
    import zipfile
    z = zipfile.ZipFile(wwz_abs_path)

    start_response('200 OK', [HTML_UTF8, last_modified])

    if DEBUG:
      log('rel_path = %r', rel_path)
      log('dir_prefix = %r', dir_prefix)

    # Suppose we have these request paths:
    #   dir/foo.wwz/spam/eggs/-wwz-index
    #   dir/foo.wwz/-wwz-index
    #
    # Then in both cases:
    #   wwz_base_url = /dir/foo.wwz
    #   wwz_abs_path = ~/www/dir/foo.wwz
    #
    #   rel_path = 
    #     -wwz-index
    #     spam/eggs/-wwz-index
    #   dir_prefix
    #     ''
    #     spam/
    #     spam/eggs/

    wwz_name = os.path.basename(wwz_abs_path)
    title = '%s : %s' % (cgi.escape(wwz_name), cgi.escape(dir_prefix))
    yield _HtmlHeader(title, wwz_base_url + '/-wwz-css')

    yield '''
    <div style="text-align: right">
      <a href="%s">wwz Status</a>
    </div>
    ''' % (wwz_base_url + '/-wwz-status')

    page_data = {
      'files': [], 'dirs': [], 

      # breadcrumb inside wwz
      'crumb2': {'anchors': [], 'urls': []} ,
      # then a breadcrumb UP TO wwz
      'crumb1': {'anchors': [], 'urls': []} ,

      # is there an index.html for this dir?
      'index_html': False
      }

    _MakeListing(page_data, z.namelist(), dir_prefix)

    n_inside = _MakeCrumb2(page_data['crumb2'], wwz_name, dir_prefix)

    _MakeCrumb1(page_data['crumb1'], n_inside, http_host, wwz_base_url)

    if DEBUG:
      from pprint import pformat
      log('%s', pformat(page_data))
      log('')

    for chunk in _Breadcrumb(page_data['crumb1'], last_slash=True):
      yield chunk

    yield '<hr/>\n'

    for chunk in _Breadcrumb(page_data['crumb2']):
      yield chunk

    for chunk in _EntriesHtml('Files', page_data['files']):
      yield chunk

    for chunk in _EntriesHtml('Dirs', page_data['dirs'], url_suffix='-wwz-index'):
      yield chunk

    if page_data['index_html']:
      yield '<hr />\n'
      yield '<p><a href=".">View index.html</a></p>\n'

    yield _HtmlFooter()

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
    """Produce HTTP response.  Called from multiple threads.

    Example:

    Given the rewrite rule in .htaccess, and URL

        http://chubot.org/wwz-test/foo.wwz/a/b/c 

    We get CGI vars:

        PATH_INFO = /a/b/c
        REQUEST_URI = /wwz-test/foo.wwz/a/b/c
        DOCUMENT_ROOT = /home/chubot/chubot.org
    """
    request_uri = environ['REQUEST_URI']
    path_info = environ.get('PATH_INFO', '')

    # PATH_INFO may be unset if you visit http://example.com/cgi-bin/wwz.py with
    # no trailng path.
    if not path_info:
      chunks = list(self.StatusPage(environ, start_response))
      tracer.Event('StatusPage-end')
      return chunks

    doc_root = environ['DOCUMENT_ROOT']

    if DEBUG:
      log('REQUEST_URI = %r', request_uri)

      log('PATH_INFO = %r', path_info)
      log('DOCUMENT_ROOT = %r', doc_root)

    n = len(path_info)
    wwz_base_url = request_uri[:-n]   # /dir/foo.wwz
    wwz_abs_path = os.path.join(doc_root, wwz_base_url[1:])

    # Use the timestamp on the whole .zip file as the Last-Modified header.  If
    # ANY file in the .zip is modified, consider the whole thing modified.  I
    # think that is fine.
    try:
      mtime = os.path.getmtime(wwz_abs_path)
    except OSError as e:
      return NotFound(start_response, "Couldn't open wwz path %r", wwz_abs_path)

    # https://stackoverflow.com/questions/225086/rfc-1123-date-representation-in-python
    last_modified = (
        'Last-Modified', formatdate(mtime, localtime=False, usegmt=True))

    rel_path = path_info[1:]  # remove leading /

    if rel_path == '-wwz-css':
      with open('wwz.css') as f:
        body = f.read()
      headers = [('Content-Type', 'text/css')]
      return Ok(start_response, headers, body)

    if rel_path == '-wwz-status':
      return list(self.StatusPage(environ, start_response))

    if rel_path == '-wwz-index' or rel_path.endswith('/-wwz-index'):
      dir_prefix = rel_path[:-len('-wwz-index')]

      return list(self.IndexListing(
        start_response, environ.get('HTTP_HOST', 'HOST'),
        wwz_base_url, wwz_abs_path,
        rel_path, dir_prefix, last_modified))


    tracer.Event('zip-begin')

    # NOTE: We are doing coarse-grained locking here.  Technically, we could
    # try not to lock when reading the zip file, but it's more complex.  We
    # don't know if two cold hits in a row go to the same zip file.  We don't
    # want to concurrent create duplicate objects.
    with self.zip_files_lock: 
      try:
        z = self.zip_files[wwz_abs_path]
      except KeyError:
        tracer.Event('open-zip')
        try:
          z = zipimport.zipimporter(wwz_abs_path)
        except zipimport.ZipImportError as e:
          return NotFound(start_response, "Couldn't open wwz path %r", wwz_abs_path)
        self.zip_files[wwz_abs_path] = z
        tracer.Event('cached-zip')

    tracer.Event('zip-end')

    # It's a file
    is_binary = False

    # The zipimporter has directory entries.  But we don't want to serve empty
    # files!
    if rel_path == '' or rel_path.endswith('/'):
      index_html = rel_path + 'index.html'
      try:
        body = z.get_data(index_html)
      except IOError as e:
        # No index.html - redirect to -wwz-index (RELATIVE URL)
        if REDIRECT_RE.match(rel_path):
          return Redirect(start_response, '-wwz-index')
        else:
          return BadRequest(start_response, 'Invalid path %r' % rel_path)

      headers = [HTML_UTF8, last_modified]
      return Ok(start_response, headers, body)

    if rel_path.endswith('.html'):
      content_type = 'text/html'
    elif rel_path.endswith('.css'):
      content_type = 'text/css'
    elif rel_path.endswith('.js'):
      content_type = 'application/javascript'
    elif rel_path.endswith('.json'):
      content_type = 'application/json'
    elif rel_path.endswith('.png'):
      content_type = 'image/png'
      is_binary = True
    elif rel_path.endswith('.tar'):  # for _release/oil.tar
      # https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types
      content_type = 'application/x-tar'
      is_binary = True
    else:
      content_type = 'text/plain'  # default

    try:
      body = z.get_data(rel_path)
    except IOError as e:
      return NotFound(start_response, 'Path %r not found in wwz archive', rel_path)

    tracer.Event('data-read')

    headers = []
    if not is_binary:
      content_type = '%s; charset=utf-8' % content_type

    # Dreamhost does send ETag.
    # Semi-unique hash gets perserved.  TODO: Bake an md5sum into .zip metadata?
    # Does this make the browser send conditional GETs?  Do crwalers ever use
    # this?
    #print 'ETag: %s' % hash(rel_path)
    headers = [('Content-Type', content_type), last_modified]

    chunks = Ok(start_response, headers, body)
    tracer.Event('request-end')

    return chunks


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

  if os.getenv('FASTCGI'):
    from flup.server.fcgi import WSGIServer
    # OLD MODULE.  I tested this and it has the same 1.0 delay, which might be
    # cilent DNS or Dreamhost.
    #from fcgi import WSGIServer

    # NOTE: debug=True shows tracebacks.
    WSGIServer(app, debug=True).run()
    #WSGIServer(app).run()

  else:
    from wsgiref.handlers import CGIHandler
    CGIHandler().run(app)


if __name__ == '__main__':
  main(sys.argv)
