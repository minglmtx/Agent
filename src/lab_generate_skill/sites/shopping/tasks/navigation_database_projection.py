"""Fixed SQL-definition projection; row values and all other options stay exact."""

SCHEMA_PROJECTION = r"""
function navigation_quote_end($sql,$at){
 $quote=$sql[$at];$n=strlen($sql);for($i=$at+1;$i<$n;$i++){
  if($sql[$i]==='\\'&&$quote!=='`'){if(++$i>=$n)throw new RuntimeException('Incomplete SQL escape');continue;}
  if($sql[$i]===$quote){if($i+1<$n&&$sql[$i+1]===$quote){$i++;continue;}return$i+1;}
 }throw new RuntimeException('Unterminated SQL quoted value');
}
function navigation_project_create($sql){
 if(!is_string($sql)||!str_starts_with($sql,'CREATE TABLE '))throw new RuntimeException('Original CREATE TABLE required');
 $n=strlen($sql);$level=0;$opened=false;$end=null;
 for($i=0;$i<$n;$i++){
  if(in_array($sql[$i],["'",'"','`'],true)){$i=navigation_quote_end($sql,$i)-1;continue;}
  if($sql[$i]==='('){$level++;$opened=true;}
  elseif($sql[$i]===')'){if(!$opened||--$level<0)throw new RuntimeException('Invalid SQL definition nesting');if($level===0){$end=$i+1;break;}}
 }
 if($end===null||!str_starts_with(substr($sql,$end),' ENGINE='))throw new RuntimeException('Original table options required');
 $out=substr($sql,0,$end);$counters=0;
 for($i=$end;$i<$n;){
  $char=$sql[$i];
  if(in_array($char,["'",'"','`'],true)){$next=navigation_quote_end($sql,$i);$out.=substr($sql,$i,$next-$i);$i=$next;continue;}
  if(($i===$end||ctype_space($sql[$i-1]))&&preg_match('/^AUTO_INCREMENT=[0-9]+(?=\s|$)/D',substr($sql,$i),$match)){
   if(++$counters>1)throw new RuntimeException('Duplicate startup counter option');$i+=strlen($match[0]);
   if($i<$n&&$sql[$i]===' ')$i++;elseif(str_ends_with($out,' '))$out=substr($out,0,-1);continue;
  }
  $out.=$char;$i++;
 }
 return$out;
}
"""
