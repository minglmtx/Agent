"""Owned browser UI for the explicit local reader; fetches native HTTP only."""
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import secrets
import threading
from urllib.parse import parse_qs, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request

from .rss_client import LocalReader, MAX_BYTES, native_url

ENTRY = '/__lab_local__/reader'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Native reader fetch cannot redirect')


def fetch_native(url, origin):
    url = native_url(url, origin)
    with build_opener(NoRedirect()).open(Request(url), timeout=30) as response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError('Native feed exceeds bounded capture')
        return dict(requested_url=url, url=response.url, status=response.status,
                    finished=True, body=body)


def document(rows, token):
    body = '<!doctype html><html lang="en"><meta charset="utf-8"><title>Local RSS reader</title><body><main><h1>Local RSS reader</h1>'
    body += '<p>Save a native feed subscription here. Saved subscriptions remain available when you reopen this reader.</p>'
    body += '<form method="post" action="'+ENTRY+'"><input type="hidden" name="csrf" value="'+token+'"><label>Feed URL <input name="url" type="text" required></label><button type="submit">Subscribe</button></form>'
    body += '<section aria-label="Saved subscriptions"><h2>Saved subscriptions</h2><ul>'
    for row in rows:
        body += '<li data-subscription-id="'+escape(row['id'],quote=True)+'"><strong>'+escape(row['parsed']['title'])+'</strong> <a href="'+escape(row['url'],quote=True)+'">'+escape(row['url'])+'</a> — '+str(row['parsed']['entries'])+' entries; '+('Active' if row['active'] else 'Inactive')+'</li>'
    return body+'</ul></section></main></body></html>'


class ReaderUI:
    def __init__(self, database, origin):
        native_url('/traces/rss', origin)
        self.database=database;self.origin=origin;self.token=secrets.token_hex(24)
        self.events=[];self.server=None;self.thread=None
        LocalReader(database)

    def dispatch(self, method, path, headers, body=b''):
        if path != ENTRY:
            return 404, {}, '<p>Not found</p>'
        client=LocalReader(self.database)
        if method == 'GET':
            snapshot=client.snapshot()
            self.events.append(dict(event='reader_reopened', records=snapshot['records']))
            return 200, {}, document(snapshot['records'], self.token)
        if method != 'POST':
            return 405, {}, '<p>Method not allowed</p>'
        if headers.get('Origin') not in (None,self.origin) or len(body)>8192:
            raise ValueError('Invalid local reader form origin or size')
        fields=parse_qs(body.decode('utf-8'),keep_blank_values=True)
        if set(fields)!={'csrf','url'} or any(len(v)!=1 for v in fields.values()) or not secrets.compare_digest(fields['csrf'][0],self.token):
            raise ValueError('Current reader form token required')
        responses=[]
        def fetch(url):
            native=fetch_native(url,self.origin);responses.append(native);return native
        before=client.snapshot()
        ident=client.subscribe(fields['url'][0],self.origin,fetch)
        after=client.snapshot()
        self.events.append(dict(event='subscription_request',id=ident,before=before,after=after,
            responses=[{**{k:v for k,v in row.items() if k!='body'},'body_hex':row['body'].hex()}for row in responses]))
        return 303, {'Location':ENTRY}, ''

    def start(self, port=0):
        if self.server is not None:
            raise ValueError('Reader already has an owned listener')
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):self.process('GET')
            def do_POST(self):self.process('POST')
            def process(self,method):
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<=length<=8192:raise ValueError('Bounded reader request required')
                    status,headers,body=owner.dispatch(method,self.path,self.headers,self.rfile.read(length))
                except Exception as error:
                    owner.events.append(dict(event='request_error',type=type(error).__name__,message=str(error)))
                    status,headers,body=502,{},'<p>Could not load or save the feed.</p>'
                raw=body.encode();self.send_response(status)
                for name,value in headers.items():self.send_header(name,value)
                self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
        server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
        server.daemon_threads=False;server.block_on_close=True
        self.server=server;self.thread=threading.Thread(target=server.serve_forever,name='owned-map-reader',daemon=False);self.thread.start()
        return server.server_address[1]

    def close(self):
        if self.server is None:return
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=10)
        if self.thread.is_alive():raise RuntimeError('Owned reader did not close')
        self.server=None;self.thread=None


def rack_initializer(port):
    if type(port)is not int or not 1<=port<=65535:raise ValueError('Owned loopback reader port required')
    return '''require "net/http"
class LabLocalReaderBridge
  def initialize(app); @app = app; end
  def call(env)
    return @app.call(env) unless env["PATH_INFO"] == "/__lab_local__/reader"
    return [405, {"Content-Type" => "text/plain"}, ["Method not allowed"]] unless ["GET", "POST"].include?(env["REQUEST_METHOD"])
    path = env["PATH_INFO"] + (env["QUERY_STRING"].to_s.empty? ? "" : "?" + env["QUERY_STRING"])
    req = (env["REQUEST_METHOD"] == "POST" ? Net::HTTP::Post : Net::HTTP::Get).new(path)
    req["Origin"] = env["HTTP_ORIGIN"] if env["HTTP_ORIGIN"]
    req["Content-Type"] = env["CONTENT_TYPE"] if env["CONTENT_TYPE"]
    if env["REQUEST_METHOD"] == "POST"
      body = env["rack.input"].read(8193)
      return [413, {"Content-Type" => "text/plain"}, ["Request too large"]] if body.bytesize > 8192
      req.body = body
    end
    response = Net::HTTP.start("127.0.0.1", PORT, nil, nil, nil, nil, :open_timeout => 5, :read_timeout => 45) { |http| http.request(req) }
    headers = {"Content-Type" => response["content-type"], "Cache-Control" => "no-store"}
    headers["Location"] = response["location"] if response["location"]
    [response.code.to_i, headers, [response.body.to_s]]
  rescue StandardError
    [502, {"Content-Type" => "text/plain"}, ["Local reader unavailable"]]
  end
end
Rails.application.config.middleware.insert_before 0, LabLocalReaderBridge
'''.replace('PORT',str(port))
