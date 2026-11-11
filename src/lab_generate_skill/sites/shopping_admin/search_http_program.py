"""Fixed local HTTP reader shared by original search snapshot and drain probes."""

SEARCH_HTTP_PHP = r"""
 function request($method,$path,$body=null,$allow404=false) {
  global $port,$until;
  $remaining=$until-hrtime(true)/1e9;if($remaining<=0)throw new RuntimeException('Original search deadline expired');
  $opts=['method'=>$method,'timeout'=>$remaining,'follow_location'=>0,'ignore_errors'=>true,'header'=>"Content-Type: application/json\r\nConnection: close\r\n"];
  if($body!==null)$opts['content']=json_encode($body,JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES);
  $stream=@fopen('http://127.0.0.1:'.$port.$path,'rb',false,stream_context_create(['http'=>$opts]));
  $headers=$http_response_header??[];
  if($stream===false)throw new RuntimeException('Search HTTP failed');
  try{$raw=stream_get_contents($stream,1048577);$meta=stream_get_meta_data($stream);}finally{fclose($stream);}
  if($raw===false||strlen($raw)>1048576||!feof_text($meta))throw new RuntimeException('Search HTTP incomplete or too large');
  if(!preg_match('/^HTTP\/[0-9.]+ ([0-9]{3})/',$headers[0]??'',$m))throw new RuntimeException('Missing HTTP status');
  $status=(int)$m[1];if($status===404&&$allow404)return null;
  if($status!==200)throw new RuntimeException('Search HTTP status '.$status.': '.substr($raw,0,2000));
  $result=json_decode($raw,true,64,JSON_THROW_ON_ERROR);if(!is_array($result))throw new RuntimeException('Expected JSON search reply');return $result;
 }
 function feof_text($meta){return is_array($meta)&&($meta['timed_out']??true)===false&&($meta['eof']??false)===true;}
"""
