"""Explicit scripted PDO substitute for hash-loop validation, not PG evidence."""

PDO_FIXTURE = r"""
class ScriptedNativeStatement {
 public $db;public $sql;public $parameters=[];
 public function __construct($db,$sql){$this->db=$db;$this->sql=$sql;}
 public function execute($parameters=[]){$this->parameters=$parameters;$this->db->statements[]=$this->sql;}
 public function closeCursor(){}
 public function fetchColumn(){
  if(str_contains($this->sql,'information_schema.table_constraints'))return json_encode([['column_name'=>'id','data_type'=>'bigint']],JSON_THROW_ON_ERROR);
  if(str_contains($this->sql,'SELECT * FROM submissions')){
   $rows=[];foreach($this->parameters as$id)$rows[]=['id'=>$id,'title'=>'synthetic row '.$id];
   return json_encode($rows,JSON_THROW_ON_ERROR);
  }
  if(str_starts_with($this->sql,'SELECT count(*) FROM submissions'))return 3;
  throw new RuntimeException('Unexpected scripted scalar SQL');
 }
 public function fetchAll($mode){
  if(!str_starts_with($this->sql,'SELECT id,md5(row_to_json(s)::text)'))throw new RuntimeException('Unexpected scripted row SQL');
  $rows=[];foreach([1,2,3]as$id)if(!$this->parameters||$id>$this->parameters[0])$rows[]=['id'=>$id,'row_md5'=>str_repeat(chr(96+$id),32)];
  return $rows;
 }
}
class ScriptedNativeDatabase {
 public $statements=[];
 public function prepare($sql){return new ScriptedNativeStatement($this,$sql);}
 public function query($sql){return new ScriptedNativeStatement($this,$sql);}
}
"""
