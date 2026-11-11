"""Fixed original native GitLab programs; never include supplied task values."""

SEED = r"""set -eu
cp -a -- /var/opt/gitlab /state/data
cp -a -- /opt/gitlab/var /state/optvar
chmod -R u+rwX /state/data /state/optvar
mkdir /state/log /state/tmp /state/var-tmp
for name in puma gitlab-rails gitaly postgresql redis gitlab-workhorse gitlab-shell nginx; do
 mkdir /state/log/"$name"
done
chmod 0700 /state/tmp /state/var-tmp /state/data/postgresql/data
mkdir -p /state/data/gitlab-workhorse/sockets
"""

SERVICE_WRAPPER = r"""#!/bin/bash
set -euo pipefail
service=$1
shift
case "$service" in gitaly|gitlab-rails|gitlab-workhorse) ;; *) exit 64;; esac
for file in /opt/gitlab/etc/"$service"/env/*; do
 [ -f "$file" ] || continue
 name=${file##*/}
 case "$name" in HOME|PYTHONPATH) continue;; esac
 export "$name=$(cat "$file")"
done
cd /var/opt/gitlab/gitlab-rails/working
exec "$@"
"""

CONFIGURE = r"""
web=Integer(ARGV.fetch(0));metrics=Integer(ARGV.fetch(1));user=ARGV.fetch(2)
raise 'Invalid private endpoints' unless (1024..65535).include?(web) && (1024..65535).include?(metrics) && web!=metrics
raise 'Invalid native peer user' unless /\A[A-Za-z_][A-Za-z0-9_-]{0,31}\z/.match?(user)
pg='/state/data/postgresql/data';pid=pg+'/postmaster.pid'
if File.exist?(pid) || File.symlink?(pid)
 s=File.lstat(pid);raise 'Unexpected seed PID entry' unless s.file? && s.nlink==1
 File.unlink(pid)
end
ident=pg+'/pg_ident.conf';before=File.read(ident)
File.write(ident,"gitlab #{user} gitlab\ngitlab #{user} gitlab-psql\n"+before)
path='/state/data/gitlab-rails/etc/gitlab.yml';text=File.read(path)
[[/^    host: [^\n]*$/,'    host: 127.0.0.1'],[/^    port: [^\n]*$/,"    port: #{web}"],[/^    email_enabled:[^\n]*$/,'    email_enabled: false']].each do |pattern,replacement|
 raise 'Original native configuration shape differs' unless text.match?(pattern)
 text=text.sub(pattern,replacement)
end
File.write(path,text)
path='/state/data/gitlab-rails/etc/puma.rb';text=File.read(path)
raise 'Original Puma TCP binding differs' unless text.include?("bind 'tcp://127.0.0.1:8080'")
raise 'Original Puma worker setting differs' unless text.include?('workers 16') || text.include?('workers: 16')
text=text.gsub("bind 'tcp://127.0.0.1:8080'",'').gsub('workers 16','workers 2').gsub('workers: 16','workers: 2')
File.write(path,text)
path='/state/data/gitaly/config.toml';text=File.read(path);pattern=/^prometheus_listen_addr = [^\n]*$/
raise 'Original Gitaly metrics setting differs' unless text.scan(pattern).length==1
File.write(path,text.sub(pattern,"prometheus_listen_addr = '127.0.0.1:#{metrics}'"))
path='/state/data/gitlab-workhorse/config.toml';text=File.read(path)
raise 'Unexpected native Workhorse shutdown policy' if text.match?(/^shutdown_timeout\s*=/)
File.write(path,"shutdown_timeout = \"10s\"\n"+text)
print 'configured'
"""

POSTGRES_READY = r"""set +e
/opt/gitlab/embedded/bin/pg_isready -h /var/opt/gitlab/postgresql >/dev/null
code=$?
case "$code" in 0) printf ready;; 1|2) printf waiting;; *) exit "$code";; esac
"""

BACKEND_READY = r"""
require 'socket';require 'timeout'
seconds=Float(ARGV.fetch(0));raise 'Invalid native readiness budget' unless seconds>0
begin
 Timeout.timeout([seconds,2.0].min) do
  UNIXSocket.open('/var/opt/gitlab/redis/redis.socket') do |redis|
   redis.write("*1\r\n$4\r\nPING\r\n")
   raise 'Unexpected native Redis health response' unless redis.gets=="+PONG\r\n"
  end
  UNIXSocket.open('/var/opt/gitlab/gitaly/gitaly.socket'){|gitaly|gitaly.close}
 end
 print 'ready'
rescue Errno::ENOENT,Errno::ECONNREFUSED,Errno::ECONNRESET,Timeout::Error
 print 'waiting'
end
"""

HTTP_READY = r"""
require 'net/http'
port=Integer(ARGV.fetch(0));seconds=Float(ARGV.fetch(1))
raise 'Invalid readiness budget' unless (1024..65535).include?(port) && seconds>0
begin
 response=Net::HTTP.start('127.0.0.1',port,nil,open_timeout:[seconds,2.0].min,read_timeout:[seconds,2.0].min) do |http|
  http.get('/users/sign_in')
 end
 print(response.code=='200' ? 'ready' : 'waiting')
rescue Errno::ECONNREFUSED,Errno::ECONNRESET,EOFError,Net::OpenTimeout,Net::ReadTimeout
 print 'waiting'
end
"""
