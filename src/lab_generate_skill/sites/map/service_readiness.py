"""Native startup probes only; no task requests, HTTP retries or observation calls."""

import base64
import json
from lab_generate_skill.domain.map_services import MapServiceSpec
from .service_commands import container
from lab_generate_skill.domain.map_runtime_inputs import MapImageRole
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.ports.native_services import NativeServices
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.map_services import MapStartupControls
from .startup_failure import MapHttpStartupFailure

POSTGRES_READY = """set +e
"$1" -h /state/run -U "$2" -d "$3" >/dev/null
code=$?
case "$code" in 0) printf ready;; 1|2) printf waiting;; *) exit "$code";; esac
"""

# Net::HTTP otherwise retries some failed idempotent requests automatically.
# One request per invocation, no proxies, redirects or recovery reissue.
HTTP_PROBE = r"""
require 'net/http'; require 'json'; require 'base64'
port=Integer(ARGV.fetch(0)); path=ARGV.fetch(1); seconds=Float(ARGV.fetch(2))
raise 'Invalid startup probe' unless (1024..65535).include?(port) && path.start_with?('/') && !path.start_with?('//') && !path.match?(/[\x00-\x20\\]/) && seconds.finite? && seconds>0 && seconds<=180
http=Net::HTTP.new('127.0.0.1',port,nil)
http.max_retries=0; http.open_timeout=[seconds,2.0].min; http.read_timeout=seconds
body=''.b; status=nil
begin
  http.start do |session|
    request=Net::HTTP::Get.new(path); request['Accept-Encoding']='identity'
    session.request(request) do |response|
      status=response.code.to_i
      lengths=response.get_fields('content-length')
      raise 'Ambiguous startup content length' if lengths && (lengths.length!=1 || !lengths[0].match?(/\A[0-9]+\z/))
      raise 'Unexpected startup content encoding' unless [nil,'identity'].include?(response['content-encoding'])
      response.read_body do |chunk|
        raise 'Startup response exceeds complete byte limit' if body.bytesize+chunk.bytesize>4*1024*1024
        body << chunk
      end
      raise 'Incomplete original startup response' if lengths && body.bytesize!=Integer(lengths[0])
    end
  end
rescue Errno::ECONNREFUSED
  raise unless status.nil? && body.empty?
  print 'waiting'; exit
end
print JSON.generate({'status'=>status,'body_base64'=>Base64.strict_encode64(body)})
"""


class MapReadiness:
    def __init__(
        self,
        spec: MapServiceSpec,
        commands: NativeCommands,
        services: NativeServices,
        limits: MapStartupControls,
    ) -> None:
        self.spec = MapServiceSpec.model_validate(spec)
        self.commands, self.services = commands, services
        self.limits = limits
        self.last_http: tuple[int, bytes] | None = None

    def postgres(self, role: MapImageRole, control: OperationControl) -> None:
        selected = {
            "nominatim": (
                "/usr/lib/postgresql/14/bin/pg_isready",
                "nominatim",
                "nominatim",
            ),
            "tiles": ("/usr/lib/postgresql/15/bin/pg_isready", "renderer", "gis"),
            "db": ("pg_isready", "openstreetmap", "openstreetmap"),
        }
        if role not in selected:
            raise ValueError("Explicit original Map database probe required")
        control = self.limits.bind(control, "postgres")
        while True:
            control.checkpoint()
            self.services.require_running()
            probe = self.limits.bind(control, "postgres_probe")
            raw = self.commands.run(
                container(self.spec, role)
                + ("sh", "-c", POSTGRES_READY, "map-postgres-ready", *selected[role]),
                probe,
            )
            if raw == b"ready":
                return
            if raw != b"waiting":
                raise ValueError("Malformed native PostgreSQL readiness reply")
            control.wait(0.25)

    def http(
        self,
        port: int,
        path: str,
        control: OperationControl,
        *,
        first_rails: bool = False,
        seconds: int = 180,
    ) -> bytes:
        if (
            type(port) is not int
            or port not in self.spec.ports.model_dump().values()
            or type(first_rails) is not bool
        ):
            raise ValueError("Original leased endpoint required")
        if (
            type(path) is not str
            or not path.startswith("/")
            or path.startswith("//")
            or any(ord(c) <= 32 or c == "\\" for c in path)
        ):
            raise ValueError("Explicit local startup request path required")
        if (
            type(seconds) is not int
            or seconds not in (30, 90, 180)
            or (
                first_rails
                and (port != self.spec.ports.web or path != "/" or seconds != 180)
            )
        ):
            raise ValueError("Original bounded Map startup phase required")
        control = self.limits.bind(
            control,
            (
                "tile_first"
                if seconds == 90
                else "tile_second" if seconds == 30 else "http"
            ),
        )
        while True:
            remaining = control.checkpoint()
            self.services.require_running()
            # A cold original tile can take longer than an ordinary health GET.
            # Keep one request within its declared phase and the caller deadline.
            tile = port == self.spec.ports.tiles and seconds in (30, 90)
            request_seconds = min(
                float(seconds) if first_rails or tile else 10.0, remaining
            )
            raw = self.commands.run(
                container(self.spec, "web")
                + ("ruby", "-e", HTTP_PROBE, str(port), path, str(request_seconds)),
                control,
            )
            if raw == b"waiting":
                control.wait(0.1)
                continue  # connection refused before any HTTP response
            value = json.loads(raw)
            if (
                type(value) is not dict
                or set(value) != {"status", "body_base64"}
                or type(value["status"]) is not int
                or not 100 <= value["status"] <= 599
                or type(value["body_base64"]) is not str
            ):
                raise ValueError("Malformed complete native HTTP readiness reply")
            body = base64.b64decode(value["body_base64"], validate=True)
            if len(body) > 4 * 1024**2:
                raise ValueError("Complete startup HTTP body exceeds bound")
            self.last_http = value["status"], body
            if value["status"] == 200:
                return body
            raise MapHttpStartupFailure(port, path, value["status"], body)
