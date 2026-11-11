"""Whole stopped native trees; retain the one original mapped log symlink."""

SOCKET_PATHS = (
    "data/postgresql/.s.PGSQL.5432",
    "data/redis/redis.socket",
    "data/gitaly/gitaly.socket",
    "data/gitlab-rails/sockets/gitlab.socket",
    "data/gitlab-workhorse/sockets/socket",
)

INVENTORY = r"""
require 'json';require 'digest'
root=ARGV.fetch(0);action=ARGV.fetch(1,'scan')
raise 'Invalid private tree' unless ['/state','/snapshot/state'].include?(root) && File.directory?(root) && !File.symlink?(root)
raise 'Invalid private tree action' unless ['scan','clear'].include?(action) && (action!='clear' || root=='/state')
rows=[];files=0;directories=0;links=0;bytes=0
visit=lambda do |path,relative|
 s=File.lstat(path);mode=s.mode&07777
 if s.symlink?
  target=File.readlink(path)
  raise 'Unexpected native symlink' unless relative=='data/nginx/logs' && target=='/var/log/gitlab/nginx'
  rows << [relative,'symlink',mode,target];links+=1
 elsif s.directory?
  rows << [relative,'directory',mode];directories+=1
  Dir.children(path).sort.each{|name|visit.call(path+'/'+name,relative=='' ? name : relative+'/'+name)}
 elsif s.file? && s.nlink==1
  digest=Digest::SHA256.file(path).hexdigest;after=File.lstat(path)
  raise 'Native file changed during inventory' unless [s.dev,s.ino,s.mode,s.nlink,s.uid,s.gid,s.size,s.mtime,s.ctime]==[after.dev,after.ino,after.mode,after.nlink,after.uid,after.gid,after.size,after.mtime,after.ctime]
  rows << [relative,'file',mode,s.size,digest];files+=1;bytes+=s.size
 else
  raise 'Special or hardlinked native snapshot entry'
 end
end
visit.call(root,'');raise 'Original mapped log symlink missing' unless links==1
if action=='clear'
 rows.each{|r|File.chmod(r[2]|0700,root+(r[0]=='' ? '' : '/'+r[0])) if r[1]=='directory'}
 rows.reverse_each do |r|
  next if r[0]==''
  path=root+'/'+r[0];r[1]=='directory' ? Dir.rmdir(path) : File.unlink(path)
 end
end
print JSON.generate({schema_version:'gitlab-tree-inventory/1',sha256:Digest::SHA256.hexdigest(JSON.generate(rows)),files:files,directories:directories,symlinks:links,bytes:bytes})
"""

CLEAR_SOCKETS = r"""
require 'json'
paths=['data/postgresql/.s.PGSQL.5432','data/redis/redis.socket','data/gitaly/gitaly.socket','data/gitlab-rails/sockets/gitlab.socket','data/gitlab-workhorse/sockets/socket']
raise 'PostgreSQL did not remove original PID file' if File.exist?('/state/data/postgresql/data/postmaster.pid') || File.symlink?('/state/data/postgresql/data/postmaster.pid')
removed=[];absent=[]
# Validate all original endpoints before the first destructive effect.
paths.each do |relative|
 path='/state/'+relative
 parent='/state';raise 'Invalid original state root' unless File.directory?(parent) && !File.symlink?(parent)
 relative.split('/')[0...-1].each do |part|
  parent+='/'+part;s=File.lstat(parent)
  raise 'Aliased original native socket parent' unless s.directory? && !s.symlink?
 end
 begin
  s=File.lstat(path);raise 'Native endpoint is not an original socket' unless s.socket?
 rescue Errno::ENOENT
  absent << relative
 end
end
(paths-absent).each{|relative|File.unlink('/state/'+relative);removed << relative}
print JSON.generate({schema_version:'gitlab-stopped-sockets/1',removed:removed,absent:absent})
"""
