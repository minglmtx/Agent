"""Complete native refs using fixed read-only Git invocations.

The pinned image's system config enables deprecated core.fsyncObjectFiles.
Only these read-only invocations skip that system config (probe4787657);
repository config and all server Git processes remain unchanged. Stderr is
still required empty and every original return code is checked.
"""

REFS_CAPTURE = r"""
require 'find'
module LabGitlabSsh
def self.git(path, *args)
  input,output,error,wait=Open3.popen3({'GIT_CONFIG_NOSYSTEM'=>'1'},'/opt/gitlab/embedded/bin/git','--git-dir='+path,*args)
  input.close; out=''.b; err=''.b
  deadline=Process.clock_gettime(Process::CLOCK_MONOTONIC)+40
  streams=[output,error]
  until streams.empty?
    left=deadline-Process.clock_gettime(Process::CLOCK_MONOTONIC)
    ready=left > 0 ? IO.select(streams,nil,nil,left) : nil
    raise 'native Git response deadline' unless ready
    ready[0].each do |io|
      data=io.read_nonblock(65536,exception:false)
      next if data == :wait_readable
      if data.nil?
        streams.delete(io); io.close
      elsif io == output
        out << data
        raise 'native Git stdout bound' if out.bytesize > 8*1024*1024
      else
        err << data
        raise 'native Git stderr bound' if err.bytesize > 65536
      end
    end
  end
  raise 'native Git exit unconfirmed' unless wait.join(2)
  [out,err,wait.value.exitstatus]
ensure
  [input,output,error].compact.each{|io|io.close unless io.closed?}
end
def self.refs
  root='/var/opt/gitlab/git-data/repositories'
  raise 'native repository root missing or aliased' unless File.directory?(root) && File.realpath(root)==root
  rows={}
  Find.find(root) do |path|
    raise 'symlink in native repository discovery' if File.symlink?(path)
    next unless path.end_with?('.git')
    raise 'non-directory repository' unless File.directory?(path)
    relative=path.delete_prefix(root+'/')
    if relative.start_with?('+gitaly/state/')
      raise 'unknown Gitaly state identity' unless relative.match?(%r{\A\+gitaly/state/(?:@hashed|@pools)/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}(?:\.wiki)?\.git\z})
      raise 'repository hidden in Gitaly state' if ['HEAD','objects','refs'].any?{|n|File.exist?(path+'/'+n)}
      Find.find(path){|p|raise 'symlink Gitaly state member' if File.symlink?(p)}
      Find.prune
    end
    bare,stderr,code=git(path,'rev-parse','--is-bare-repository')
    raise 'native bare Git validation failed: '+JSON.generate({'repository'=>relative,'exit_status'=>code,'stdout'=>bare,'stderr'=>stderr}) unless code==0 && stderr.empty? && bare.strip=='true'
    output,stderr,code=git(path,'for-each-ref','--format=%(refname) %(objectname)')
    raise 'native refs read failed' unless code==0 && stderr.empty?
    refs={}
    output.each_line do |line|
      name,oid=line.strip.split(' ',2)
      raise 'duplicate or malformed native ref' unless name && oid && !refs.key?(name) && oid.match?(/\A(?:[0-9a-f]{40}|[0-9a-f]{64})\z/)
      refs[name]=oid
    end
    symbolic,stderr,symbol_code=git(path,'symbolic-ref','-q','HEAD')
    raise 'native symbolic HEAD read failed' unless [0,1].include?(symbol_code) && stderr.empty?
    symbolic=symbol_code==0 ? symbolic.strip : nil
    head,stderr,head_code=git(path,'rev-parse','--verify','--quiet','HEAD')
    if head_code==0
      head=head.strip
      raise 'native HEAD identity' unless stderr.empty? && head.match?(/\A(?:[0-9a-f]{40}|[0-9a-f]{64})\z/)
      raise 'native HEAD/ref mismatch' if symbolic && refs[symbolic]!=head
    else
      # A valid unborn branch is the sole allowed missing HEAD. Detached,
      # broken, unreadable and dangling heads remain capture failures.
      raise 'native HEAD unavailable' unless head_code==1 && stderr.empty? && symbolic &&
        symbolic.start_with?('refs/heads/') && !refs.key?(symbolic) && head.empty?
      head=nil
    end
    rows[relative]={'head'=>head,'symbolic_head'=>symbolic,'refs'=>refs}
    Find.prune
  end
  raise 'empty native repository discovery' if rows.empty?
  {'version'=>'gitlab-all-native-refs-v1','complete'=>true,'repositories'=>rows}
end
end
"""
