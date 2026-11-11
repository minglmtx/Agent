"""Capture actual local-browser downloads; never sends images/files to a model."""
import csv,hashlib,io,re,uuid
from pathlib import Path
from decimal import Decimal,InvalidOperation
from xml.etree import ElementTree


def spreadsheetml_rows(raw):
    if re.search(br'<!\s*(?:DOCTYPE|ENTITY)\b',raw,re.I):raise ValueError('XML declarations with entities are not accepted')
    ns='{urn:schemas-microsoft-com:office:spreadsheet}'
    root=ElementTree.fromstring(raw)
    if root.tag!=ns+'Workbook':raise ValueError('Expected an Excel XML Workbook')
    tables=root.findall('.//'+ns+'Worksheet/'+ns+'Table')
    if len(tables)!=1:raise ValueError('Expected exactly one export worksheet')
    rows=[]
    for row in tables[0].findall(ns+'Row'):
        values=[]
        for cell in row.findall(ns+'Cell'):
            index=int(cell.get(ns+'Index',len(values)+1))
            if index<=len(values) or index>1000:raise ValueError('Invalid spreadsheet cell index')
            values.extend(['']*(index-len(values)-1))
            data=cell.find(ns+'Data');values.append(''.join(data.itertext()) if data is not None else '')
        rows.append(values)
    if not rows or not rows[0] or len(set(rows[0]))!=len(rows[0]) or any(not h for h in rows[0]):raise ValueError('Missing or duplicated export columns')
    columns=rows[0];result=[]
    for row in rows[1:]:
        if len(row)>len(columns):raise ValueError('Too many cells in export row')
        row=row+['']*(len(columns)-len(row));result.append(dict(zip(columns,row)))
    return columns,result


def attach(page,directory):
    if hasattr(page,'_admin_downloads'):return
    page._admin_downloads=[]
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    def capture(download):
        name=Path(download.suggested_filename).name
        path=directory/(uuid.uuid4().hex+'-'+re.sub(r'[^a-zA-Z0-9_.-]','_',name))
        record={'suggested_filename':name,'url':download.url,'path':str(path),'complete':False}
        try:
            download.save_as(path)
            record['bytes']=path.stat().st_size
            if record['bytes']>20_000_000:raise ValueError('download_exceeds_validation_size_limit')
            raw=path.read_bytes();record['sha256']=hashlib.sha256(raw).hexdigest()
            if name.lower().endswith('.csv'):
                reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
                record.update(format='csv',columns=reader.fieldnames,rows=list(reader))
            elif name.lower().endswith('.pdf'):
                from .admin_pdf import extract_pdf
                record.update(extract_pdf(raw))
            elif name.lower().endswith('.xml'):
                columns,rows=spreadsheetml_rows(raw)
                record.update(format='spreadsheetml',columns=columns,rows=rows)
            else:record['format']='unsupported'
            record['complete']=True
        except Exception as exc:record['error']=type(exc).__name__+': '+str(exc)
        page._admin_downloads.append(record)
    page.on('download',capture)


def csv_matches(download,spec,reference):
    # Historical API name retained; declared Excel XML exports use the same exact-set contract.
    if spec.get('export_format','csv') not in ('csv','spreadsheetml'):return False
    if not download.get('complete') or download.get('format')!=spec.get('export_format','csv'):return False
    if not download.get('bytes') or not isinstance(download.get('rows'),list):return False
    columns=spec['export_columns']
    if any(c not in (download.get('columns') or []) for c in columns):return False
    rows=download['rows']
    if len(rows)!=len(reference):return False
    remaining=list(reference)
    def same(field,actual,expected):
        if field=='grand_total':
            try:return Decimal(re.sub(r'[^0-9.-]','',str(actual)))==Decimal(str(expected))
            except InvalidOperation:return False
        return str(actual).strip()==str(expected).strip()
    for row in rows:
        idx=next((i for i,ref in enumerate(remaining) if all(same(field,row.get(column),ref.get(field)) for column,field in columns.items())),None)
        if idx is None:return False
        remaining.pop(idx)
    return not remaining
