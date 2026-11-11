"""Independent all31 protection for the ordinary owned-quote lifecycle.

Only the explicitly owned quote family is delegated to its existing full-field
task checks. Every foreign original field, clock, owner and PK stays protected.
"""
import json,re
from pathlib import Path
from .shopping_search_protection import TABLES as LEGACY22

TABLES=LEGACY22|{'quote','quote_address','quote_payment','sales_order_status_history','review','review_detail','review_store','review_entity_summary','rating_option_vote'}
VERSION='shopping-owned-quote-independent-foreign31-v1'

def validate(value):
 if not isinstance(value,dict)or value.get('version')!=VERSION or value.get('db_writes')!=0 or value.get('full31_scans')!=1 or value.get('same_readonly_transaction')is not True:raise ValueError('Fresh consistent read-only owned/foreign31 capture required')
 owner=value.get('owner',{});state=value.get('owned_quote_state',{})
 if set(owner)!={'quote_id','customer_id'}or any(type(owner.get(k))is not int or owner[k]<=0 for k in owner)or any(state.get(k)!=owner[k]for k in owner):raise ValueError('Exact native quote/account binding required')
 strict=value.get('strict_foreign31',{});complete=value.get('complete_physical31',{})
 if strict.get('version')!='shopping-foreign31-all-fields-v1'or strict.get('ignored_columns')!=[]or strict.get('excluded_owned_quote_id')!=owner['quote_id']or strict.get('excluded_owned_item_ids')!=[r['item_id']for r in state.get('items',[])]:raise ValueError('Explicit exact owned quote/item exclusion required')
 if complete.get('version')!='shopping-complete-native-query-full-rows-v1'or complete.get('statement_budget_seconds')!=20:raise ValueError('Complete physical31 scope required')
 for block in(strict,complete):
  if set(block.get('tables',{}))!=TABLES:raise ValueError('Every strict native table required')
  for table,row in block['tables'].items():
   if type(row.get('rows'))is not int or row['rows']<0 or not re.fullmatch('[0-9a-f]{64}',row.get('sha256',''))or not row.get('primary_key')or not set(row['primary_key'])<=set(row.get('columns',[])):raise ValueError('Every native row/field/PK required')
   if block is complete and(row.get('ignored_columns')!=[]or type(row.get('chunks'))is not int or row['chunks']<1):raise ValueError('No ignored physical column or incomplete chunks')
   if block is strict and row.get('excluded_current_quote_rows')is not(table in {'quote','quote_address','quote_payment','quote_item','quote_item_option'}):raise ValueError('Foreign exclusion outside exact owned quote family')
 if set(state.get('foreign_protected',{}))not in(LEGACY22,TABLES):raise ValueError('Explicit unchanged legacy foreign scope required')
 if any(row!=strict['tables'][t]for t,row in state['foreign_protected'].items()):raise ValueError('Legacy compatibility cannot weaken strict foreign rows')
 return value

def capture(site,email,*,strict_legacy31=False):
 php=Path(__file__).with_suffix('.php')
 raw=site.command(['php','-d','memory_limit=1024M','-r',php.read_text().removeprefix('<?php'),json.dumps({'email':email,'strict_legacy31':strict_legacy31})],capture_output=True,text=True,timeout=240)
 return validate(json.loads(raw.stdout))

def unchanged(before,after):
 validate(before);validate(after)
 return before['owner']==after['owner']and before['strict_foreign31']==after['strict_foreign31']
