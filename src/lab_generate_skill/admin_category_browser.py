"""Read-only native legacy grid capture; private control actions are separate."""
from bs4 import BeautifulSoup
from urllib.parse import urlsplit
import re,hashlib
from .admin_category_rules import request_filter

def parse_grid(html):
 dom=BeautifulSoup(html,'html.parser');tables=dom.select('#catalog_category_products_table')
 if len(tables)!=1:raise ValueError('unique_native_category_grid_required')
 table=tables[0];headers=None
 for tr in table.select('thead tr'):
  labels=[x.get_text(' ',strip=True)for x in tr.find_all('th',recursive=False)]
  if 'ID'in labels and'SKU'in labels:headers=labels;break
 if headers is None:raise ValueError('native_grid_header_identity_missing')
 rows=[]
 for tr in table.select('tbody tr'):
  cells=tr.find_all('td',recursive=False)
  if len(cells)==1 and cells[0].get('colspan'):continue
  if not cells:continue
  if len(cells)!=len(headers):raise ValueError('native_grid_row_shape_changed')
  values={h:cells[i].get_text(' ',strip=True)for i,h in enumerate(headers)}
  if not re.fullmatch(r'[0-9]+',values['ID']):raise ValueError('native_product_row_identity_missing')
  rows.append(dict(id=values['ID'],sku=values['SKU']))
 return rows

def install(page,origin):
 receipts=[]
 def completed(request):
  try:scope=request_filter(request.url,request.post_data,origin)
  except ValueError as e:receipts.append(dict(error=str(e),response_valid=False));return
  if scope is None:return
  r=dict(scope,response_valid=False);receipts.append(r)
  try:
   response=request.response();r['status']=response.status if response else None
   if not response or response.status!=200:raise ValueError('native_grid_http_error')
   body=response.body();r['body_sha256']=hashlib.sha256(body).hexdigest();r['rows']=parse_grid(body.decode('utf-8'));r['response_valid']=True
  except Exception as e:r['error']=type(e).__name__+':'+str(e)
 def failed(request):
  try:scope=request_filter(request.url,request.post_data,origin)
  except ValueError as e:receipts.append(dict(error=str(e),response_valid=False));return
  if scope is not None:receipts.append(dict(scope,error='native_grid_request_failed',response_valid=False))
 page.on('requestfinished',completed);page.on('requestfailed',failed);return receipts

def capture(page):
 try:
  grid=page.locator('#catalog_category_products');assert grid.count()==1
  html=grid.inner_html();rows=parse_grid(html);m=re.search(r'/catalog/category/(?:edit|grid)/id/(\d+)(?:/|$)',urlsplit(page.url).path)
  if not m:raise ValueError('current_category_url_identity_missing')
  sku=grid.locator('[data-role="filter-form"] input[name="sku"]').input_value();membership=grid.locator('[data-role="filter-form"] select[name="in_category"]').input_value()
  text=grid.inner_text();counts=re.findall(r'\b([0-9,]+)\s+records?\s+found\b',text,re.I)
  if len(counts)!=1:raise ValueError('native_total_record_count_missing')
  total=int(counts[0].replace(',',''));assert total>=len(rows)
  return dict(category_id=m.group(1),sku_filter=sku,membership_filter=membership,rows=rows,total_records=total,complete=total==len(rows),page_valid=True,html_sha256=hashlib.sha256(html.encode()).hexdigest())
 except Exception as e:return dict(capture_error=type(e).__name__+':'+str(e))
