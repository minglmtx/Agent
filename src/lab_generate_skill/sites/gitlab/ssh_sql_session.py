"""Fixed Ruby read-only PostgreSQL session inside the original site worker.

NUL framing retains physical JSON newlines. This selected collector uses one
repeatable-read snapshot for users, keys and guards, unlike the old separate
READ COMMITTED sessions. No SQL or rows are exported through Actor tools.
"""

SQL_SESSION = r"""
require 'json'; require 'open3'; require 'securerandom'; require 'digest'
module LabGitlabSsh
class SqlSession
  PSQL = ['/opt/gitlab/embedded/bin/psql', '-h', '/var/opt/gitlab/postgresql',
          '-U', 'gitlab', '-d', 'gitlabhq_production', '-X', '-q', '-A', '-t',
          '-0', '-w', '-v', 'ON_ERROR_STOP=1'].freeze
  def initialize
    @input, @output, @error, @wait = Open3.popen3(*PSQL)
    @buffer = ''.b; @stderr = ''.b; @sequence = 0
    @token = SecureRandom.hex(24)
    deadline = now + 40
    send_sql("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;\n" +
             "SET LOCAL statement_timeout='20s';\n" +
             "SELECT json_build_object('token','#{@token}','ready',true);\n", deadline)
    raise 'native SQL startup identity' unless receive(deadline) == {'token'=>@token,'ready'=>true}
  rescue Exception => primary
    finish(primary) if @input
    raise
  end
  def now; Process.clock_gettime(Process::CLOCK_MONOTONIC); end
  def send_sql(value, deadline)
    data = value.b
    until data.empty?
      left = deadline-now
      raise 'native SQL request deadline' unless left > 0 && IO.select(nil, [@input], nil, left)
      count = @input.write_nonblock(data, exception: false)
      next if count == :wait_writable
      data = data.byteslice(count..-1) || ''.b
    end
  end
  def receive(deadline)
    loop do
      if (index = @buffer.index("\0"))
        raw = @buffer.byteslice(0,index); @buffer = @buffer.byteslice(index+1..-1) || ''.b
        next if raw.strip.empty?
        raise 'native SQL oversized record' if raw.bytesize > 8*1024*1024
        return JSON.parse(raw)
      end
      left = deadline-now
      ready = left > 0 ? IO.select([@output,@error].reject(&:closed?),nil,nil,left) : nil
      raise 'native SQL response deadline' unless ready
      ready[0].each do |io|
        part = io.read_nonblock(65536, exception:false)
        next if part == :wait_readable
        if part.nil?
          io.close
          raise 'native SQL incomplete stdout' if io == @output
        elsif io == @output
          @buffer << part
          raise 'native SQL response bound' if @buffer.bytesize > 8*1024*1024
        else
          @stderr << part
          raise 'native SQL stderr bound' if @stderr.bytesize > 65536
        end
      end
    end
  end
  def select(sql)
    raise 'one fixed bounded SELECT required' unless sql.is_a?(String) && sql.start_with?('SELECT ') &&
      sql.bytesize <= 65536 && !sql.match?(/[;\n\r\\\x00]/)
    deadline = now+40
    send_sql("SELECT json_build_object('token','#{@token}','sequence',#{@sequence}," +
             "'rows',COALESCE(json_agg(q),'[]'::json)) FROM (#{sql}) q;\n", deadline)
    value = receive(deadline)
    raise 'native SQL response identity' unless value.is_a?(Hash) && value.keys.sort == ['rows','sequence','token'] &&
      value['token'] == @token && value['sequence'].instance_of?(Integer) && value['sequence'] == @sequence &&
      value['rows'].is_a?(Array) && value['rows'].all?{|r| r.is_a?(Hash)}
    @sequence += 1
    value['rows']
  end
  def close
    return if @closed
    @closed = true
    @input.close unless @input.closed?
    # EOF rolls the read-only transaction back. Outer original process/domain
    # supervision still owns termination if the client cannot exit normally.
    raise 'native SQL client exit unconfirmed' unless @wait.join(2)
    raise 'native SQL client failed' unless @wait.value.success?
    raise 'native SQL unexpected trailing output' unless @buffer.strip.empty? && @output.read.to_s.strip.empty?
    @stderr << @error.read.to_s unless @error.closed?
    raise 'native SQL stderr bound' if @stderr.bytesize > 65536
    raise 'native SQL unexpected stderr' unless @stderr.empty?
  ensure
    [@input,@output,@error].compact.each{|io| io.close unless io.closed?}
  end
  def finish(primary)
    close
  rescue Exception => cleanup
    STDERR.write(JSON.generate({'phase'=>'native_sql_close',
      'primary_error'=>primary ? {'class'=>primary.class.name,'message'=>primary.message} : nil,
      'cleanup_error'=>{'class'=>cleanup.class.name,'message'=>cleanup.message}})+"\n")
    raise cleanup unless primary
  end
end
end
"""
