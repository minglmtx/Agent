"""Fixed full-row traversal and the original sixteen protected-table hashes."""

from .tasks.ssh_key_state import AUTH_COLUMNS, PROTECTED_TABLES
import json

SQL_CAPTURE = (
    "module LabGitlabSsh\nAUTH = "
    + json.dumps(AUTH_COLUMNS)
    + ".freeze\nTABLES = "
    + json.dumps(PROTECTED_TABLES)
    + r""".freeze
def self.ident(value)
  raise 'native SQL identifier' unless value.is_a?(String) && value.match?(/\A[A-Za-z_][A-Za-z0-9_]*\z/)
  '"'+value+'"'
end
def self.columns(db, table)
  rows = db.select("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='#{table}' ORDER BY ordinal_position")
  names = rows.map{|r| r['column_name']}
  raise 'complete native schema absent' if names.empty? || names.uniq != names
  names.each{|n| ident(n)}
  rows
end
def self.count(db, table)
  rows = db.select('SELECT COUNT(*) AS n FROM '+ident(table))
  n = rows.length == 1 ? rows[0]['n'] : nil
  raise 'complete native row count' unless n.instance_of?(Integer) && n >= 0
  n
end
def self.table(db, table)
  names = columns(db,table).map{|r|r['column_name']}
  raise 'native id schema required' unless names.include?('id')
  total = count(db,table); rows=[]; cursor=0
  while rows.length < total
    part = db.select('SELECT row_to_json(t) AS row FROM '+ident(table)+' t WHERE id>'+cursor.to_s+' ORDER BY id LIMIT 256')
    raise 'incomplete native table traversal' unless part.length == [256,total-rows.length].min
    part.each do |item|
      row=item['row']; id=row.is_a?(Hash) ? row['id'] : nil
      raise 'complete native ordered row required' unless row.is_a?(Hash) && row.keys.sort == names.sort && id.instance_of?(Integer) && id > cursor
      cursor=id; rows << row
    end
  end
  raise 'native table changed during traversal' unless count(db,table) == total
  {'table'=>table,'columns'=>names,'rows'=>rows,'row_count'=>total,'complete'=>true}
end
def self.unique_key_query(table)
  raise 'unknown protected table' unless TABLES.include?(table)
  "SELECT i.indexrelid, i.indisprimary, array_agg(a.attname ORDER BY k.ord) AS names FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid JOIN LATERAL unnest(i.indkey) WITH ORDINALITY k(attnum,ord) ON true JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum WHERE c.oid='public.#{table}'::regclass AND i.indisunique AND i.indpred IS NULL AND i.indexprs IS NULL AND a.attnotnull GROUP BY i.indexrelid,i.indisprimary,i.indkey HAVING count(*)=array_length(i.indkey::smallint[],1) ORDER BY i.indisprimary DESC,i.indexrelid LIMIT 1"
end
def self.guard(db, account_id)
  result={}
  TABLES.each do |table|
    schema=columns(db,table); names=schema.map{|r|r['column_name']}
    keys=db.select(unique_key_query(table)); key=keys.length == 1 ? keys[0]['names'] : nil
    raise 'native unique nonnullable key absent' unless key.is_a?(Array) && !key.empty? && key.uniq == key && (key-names).empty?
    order=key.map{|n|ident(n)}.join(','); types=schema.to_h{|r|[r['column_name'],r['data_type']]}
    keyset=key.all?{|n| ['smallint','integer','bigint'].include?(types[n])}
    total=count(db,table); offset=0; cursor=nil; hash=Digest::SHA256.new
    expression='row_to_json(t)::text'
    if table == 'users'
      subtract=AUTH.map{|n|"-'#{n}'"}.join
      expression="(CASE WHEN t.id=#{account_id} THEN to_jsonb(t)#{subtract} ELSE to_jsonb(t) END)::text"
    end
    while offset < total
      projection='md5('+expression+') AS digest'
      clause=''
      if keyset
        projection+=',json_build_array('+order+') AS native_key'
        clause=' WHERE ('+order+')>('+cursor.join(',')+')' if cursor
      end
      sql='SELECT '+projection+' FROM '+ident(table)+' t'+clause+' ORDER BY '+order
      sql+=' OFFSET '+offset.to_s unless keyset
      part=db.select(sql+' LIMIT 2048')
      raise 'incomplete native guard chunk' unless part.length == [2048,total-offset].min
      part.each do |row|
        raise 'native full-row digest' unless row['digest'].is_a?(String) && row['digest'].match?(/\A[0-9a-f]{32}\z/)
        if keyset
          current=row['native_key']
          raise 'native guard key order' unless current.is_a?(Array) && current.length == key.length &&
            current.all?{|x|x.instance_of?(Integer) && x >= -(1<<63) && x < (1<<63)} &&
            (cursor.nil? || (current <=> cursor) == 1)
          cursor=current
        end
        hash.update(row['digest']+"\n")
      end
      offset+=part.length
    end
    raise 'native guard changed during traversal' unless count(db,table) == total
    result[table]={'rows'=>total,'columns'=>names,'key'=>key,'sha256'=>hash.hexdigest}
  end
  result
end
end
"""
)
