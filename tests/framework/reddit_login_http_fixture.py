"""Original-template-shaped loopback fixture; never a native Postmill DB."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from urllib.parse import parse_qs

LOGIN = b"""<html><title>Log in</title><form action="/login_check" method="POST">
<input type="hidden" name="_csrf_token" value="engineering-csrf">
<label for="login-username">Username</label><input name="_username" id="login-username" required>
<label for="login-password">Password</label><input type="password" name="_password" id="login-password" required>
<button type="submit">Log in</button></form></html>"""
SUBMIT = """<form action="/submit" method="post" enctype="multipart/form-data">
<label>Photo<input type="file" name="submission[image]" accept="image/*"></label>
<label>Title<textarea name="submission[title]"></textarea></label>
<label>Forum<select name="submission[forum]"><option value="">Choose one</option><option value="1">EarthPorn</option></select></label>
<input type="hidden" name="submission[_token]" value="engineering-submit-token">
<button type="submit">Create submission</button></form>"""


class RedditLoginFixture:
    """One fake credential pair, no password/POST body retained in diagnostics."""

    def __init__(self, *, wrong_account: bool = False) -> None:
        self.posts: list[str] = []
        self.gets: list[str] = []
        self.server: ThreadingHTTPServer
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                pass

            def respond(self, status: int, body: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                owner.gets.append(self.path)
                if self.path == "/login":
                    self.respond(200, LOGIN)
                    return
                if self.path not in ("/", "/submit"):
                    self.respond(404, b"Not found")
                    return
                if "engineering-session=1" not in self.headers.get("Cookie", ""):
                    self.send_response(302)
                    self.send_header("Location", "/login")
                    self.end_headers()
                    return
                username = "different-user" if wrong_account else "native-user"
                menu = (
                    '<ul class="site-nav__user-menu"><li class="dropdown"><button class="dropdown__toggle"><strong class="no-mobile">'
                    + username
                    + '</strong></button><ul><li><form action="/log_out?token=x" method="POST"><button>Log out</button></form></li></ul></li></ul>'
                )
                self.respond(
                    200,
                    (
                        "<html><title>Submit</title>"
                        + menu
                        + (SUBMIT if self.path == "/submit" else "Logged in")
                        + "</html>"
                    ).encode(),
                )

            def do_POST(self) -> None:
                owner.posts.append(self.path)
                size = int(self.headers.get("Content-Length", "0"))
                if size > 4096:
                    self.respond(413, b"Too large")
                    return
                data = parse_qs(self.rfile.read(size).decode())
                if self.path != "/login_check" or data != {
                    "_csrf_token": ["engineering-csrf"],
                    "_username": ["native-user"],
                    "_password": ["engineering-private-password"],
                }:
                    self.respond(403, b"Invalid fixture login")
                    return
                self.send_response(302)
                self.send_header("Location", "/")
                self.send_header(
                    "Set-Cookie",
                    "engineering-session=1; HttpOnly; SameSite=Lax; Path=/",
                )
                self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/"

    def __enter__(self) -> "RedditLoginFixture":
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError("Original login fixture thread did not stop")
