"""Private read-only all-original31 protection for review/contact episodes."""
import json,re
from pathlib import Path

COVERAGE='Every row and column of explicit account/address/order/payment/cart/coupon/history/review tables. No ignored columns. Sessions, visitors, guest compare collection and authentication log are mutable runtime metadata and not claimed protected.'
TABLES=frozenset(('customer_entity','customer_entity_datetime','customer_entity_decimal','customer_entity_int','customer_entity_text','customer_entity_varchar','customer_address_entity','customer_address_entity_datetime','customer_address_entity_decimal','customer_address_entity_int','customer_address_entity_text','customer_address_entity_varchar','sales_order','sales_order_item','sales_order_address','sales_order_payment','quote_item','quote_item_option','salesrule','salesrule_coupon','salesrule_customer_group','salesrule_website','quote','quote_address','quote_payment','sales_order_status_history','review','review_detail','review_store','review_entity_summary','rating_option_vote'))
def validate_full31(value):
 if not isinstance(value,dict)or value.get('version')!='shopping-complete-native-query-full-rows-v1'or value.get('statement_budget_seconds')!=20 or value.get('coverage')!=COVERAGE or set(value.get('tables',{}))!=TABLES:
  raise ValueError('Exact all-original31 native protection required')
 for row in value['tables'].values():
  if row.get('ignored_columns')!=[]or type(row.get('rows'))is not int or row['rows']<0 or row.get('chunks')!=row['rows']//1024+1 or not row.get('primary_key')or not set(row['primary_key'])<=set(row.get('columns',[]))or not re.fullmatch('[0-9a-f]{64}',row.get('sha256','')):
   raise ValueError('All native fields/PKs including clocks must remain covered')
 return value

def require_proof(c,proof):
 if c['offline_training']['mode']not in('review','contact'):return
 states=[]
 for row in proof.get('cycles',[]):
  before=validate_full31(row.get('complete_original_before'));after=validate_full31(row.get('complete_original_after'))
  if before!=after or row.get('complete_original_restored')is not True or row.get('complete_original_changed_tables')!=[]:
   raise ValueError('Actual complete original31 two-cold restoration missing')
  states.append(before)
 if len(states)!=2 or states[0]!=states[1]:raise ValueError('Same all-original31 baseline required in two cold instances')

def command(site,payload):
 php=Path(__file__).with_suffix('.php')
 output=site.command(['php','-r',php.read_text().removeprefix('<?php'),json.dumps(payload)],capture_output=True,text=True,timeout=240)
 return json.loads(output.stdout)

def capture(site,email,c):
 s=c['offline_training'];value=command(site,{'operation':'capture','mode':s['mode'],'email':email,'product_id':s.get('product_id')});validate_full31(value['full31_before']);return value

def terminal(site,baseline,review=None):
 ids=[] if review is None else [r['review_id']for r in review['reviews']['added']]
 value=command(site,{'operation':'terminal','baseline':baseline,'new_review_ids':ids})
 if value.get('target_write_violation')is True:
  if value.get('integrity')is not False or value.get('db_writes')!=0:raise ValueError('Invalid negative target-write capture')
  return value
 validate_full31(value['canonical_original31'])
 if value.get('db_writes')!=0 or type(value.get('integrity'))is not bool or value['integrity']!=(value['canonical_original31']==baseline['full31_before']):raise ValueError('Read-only complete31 integrity result mismatch')
 return value
