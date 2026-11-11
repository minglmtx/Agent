"""Explicit private Map extension exposing genuine mail through the native origin.

Install before Rails starts and before capturing the reset baseline. This only
adds a mailbox link and read-only proxy; native signup and confirmation remain
unchanged. It does not constitute reset verification or task admission.
"""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

INBOX_PATH = '/__lab_local__/account-inbox'
HEADER_ANCHOR = "  <nav class='secondary'>"
# Native application.js sums the widths of every direct header child to
# choose its responsive layout. Bootstrap's .nav-link alone is display:block:
# outside a nav this consumes the full header width and forces small-nav,
# hiding both native direction forms even on a desktop viewport.
LINK = ('  <a class="nav-link d-inline-block" href="' + INBOX_PATH
        + '" data-local-account-inbox="true">Local account inbox</a>\n')


class NativeInboxExtension:
    def __init__(self, frontend_state, inbox):
        self.app = Path(frontend_state) / 'app'
        self.inbox = inbox
        self.originals = {}
        self.installed = {}

    def install(self):
        if self.installed or self.inbox.closed or not self.inbox.thread.is_alive():
            raise ValueError('A new extension and live owned inbox are required')
        endpoint = urlsplit(self.inbox.url)
        if (endpoint.scheme != 'http' or endpoint.hostname != '127.0.0.1'
                or endpoint.port != self.inbox.server.server_port
                or endpoint.path != '/inbox' or endpoint.query or endpoint.fragment
                or endpoint.username or endpoint.password):
            raise ValueError('Exact owned inbox endpoint required')
        header = self.app / 'app/views/layouts/_header.html.erb'
        controller = self.app / 'app/controllers/lab_local_account_inbox_controller.rb'
        routes = self.app / 'config/initializers/zz_local_account_inbox.rb'
        if header.is_symlink() or not header.is_file():
            raise ValueError('Native regular header required')
        source = header.read_bytes()
        text = source.decode()
        if text.count(HEADER_ANCHOR) != 1 or 'data-local-account-inbox' in text:
            raise ValueError('Native header changed or inbox already installed')
        for path in (controller, routes):
            if path.exists() or path.is_symlink() or not path.parent.is_dir():
                raise ValueError('Private inbox source path unavailable: ' + str(path))
        # The endpoint is an owned constant, never taken from browser parameters.
        # Net::HTTP redirects are not followed, and failed mail delivery remains
        # an explicit unavailable state instead of an empty successful mailbox.
        ruby = '''require "net/http"
require "timeout"

class LabLocalAccountInboxController < ActionController::Base
  def index
    response_body = +""
    Timeout.timeout(5) do
      target = URI(__ENDPOINT__)
      transport = Net::HTTP.new(target.host, target.port, nil)
      transport.open_timeout = 1
      transport.read_timeout = 2
      transport.max_retries = 0
      transport.request(Net::HTTP::Get.new(target.request_uri)) do |response|
        raise IOError, "Native inbox unavailable" unless response.code == "200"
        response.read_body do |chunk|
          response_body << chunk
          raise IOError, "Native inbox exceeds response budget" if response_body.bytesize > 4194304
        end
      end
    end
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    render :html => response_body.html_safe, :layout => false
  rescue StandardError
    response.headers["Cache-Control"] = "no-store"
    render :plain => "Native local inbox unavailable; no confirmation has been performed.", :status => 503
  end
end
'''.replace('__ENDPOINT__', json.dumps(self.inbox.url))
        route_source = ('# Explicit local training environment extension; GET only.\n'
                        'Rails.application.routes.append do\n'
                        '  get "' + INBOX_PATH + '" => "lab_local_account_inbox#index"\nend\n')
        changes = {header: text.replace(HEADER_ANCHOR, LINK + HEADER_ANCHOR).encode(),
                   controller: ruby.encode(), routes: route_source.encode()}
        self.originals = {header: source, controller: None, routes: None}
        try:
            for path, payload in changes.items():
                path.write_bytes(payload)
                self.installed[path] = payload
        except BaseException:
            self.close()
            raise
        return dict(version='native-map-account-inbox-frontend-v1',
                    public_path=INBOX_PATH, original_snapshot_equivalence=False,
                    automatic_confirmation=False, reset_verified=False,
                    files={str(p.relative_to(self.app)): hashlib.sha256(b).hexdigest()
                           for p, b in self.installed.items()})

    def close(self):
        # Check all sources before restoring any, so unexpected concurrent edits
        # are never overwritten. The caller separately owns/stops the mail server.
        for path, payload in self.installed.items():
            if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
                raise ValueError('Installed inbox source changed: ' + str(path))
        count = len(self.installed)
        for path in self.installed:
            original = self.originals[path]
            if original is None:
                path.unlink()
            else:
                path.write_bytes(original)
        self.installed.clear()
        return dict(restored_files=count)
