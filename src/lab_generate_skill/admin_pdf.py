"""Validate actual downloaded PDF document identities; no screenshot or LLM judge."""
import io,os,re,sys
from pathlib import Path

def extract_pdf(raw):
    if not raw.startswith(b'%PDF-'):raise ValueError('Not a PDF document')
    try:from pypdf import PdfReader
    except ModuleNotFoundError:
        dependency=Path(os.environ['LMTX_ROOT'])/'environments/admin-pdf-v1'
        if not (dependency/'pypdf').is_dir():raise RuntimeError('Install declared pypdf dependency before admitting PDF tasks')
        sys.path.insert(0,str(dependency));from pypdf import PdfReader
    reader=PdfReader(io.BytesIO(raw),strict=True)
    if reader.is_encrypted or not 1<=len(reader.pages)<=200:raise ValueError('Unsupported PDF encryption or page count')
    texts=[p.extract_text() or '' for p in reader.pages]
    if not any(t.strip() for t in texts):raise ValueError('PDF has no extractable document text')
    return {'format':'pdf','pages':len(texts),'text':'\n'.join(texts)}

def matches_pdf(download,spec,references):
    if not download.get('complete') or download.get('format')!='pdf' or not download.get('bytes'):return False
    text=download.get('text','');kind=spec['document_kind']
    patterns={'invoice':r'Invoice\s*#','packing_slip':r'(?:Shipment|Packing Slip)\s*#','shipping_label':r'Tracking','credit_memo':r'Credit\s*Memo\s*#'}
    kinds=spec.get('required_document_kinds',[kind])
    if not all(re.search(patterns[k],text,re.I) for k in kinds):return False
    observed=set(re.findall(r'Order\s*#\s*(\d+)',text,re.I))
    expected={str(r['order_increment_id'] if spec.get('entity')=='shipment' else r['increment_id']) for r in references}
    # An exact order set prevents unrelated or partial multi-order printouts.
    return observed==expected and bool(expected)
