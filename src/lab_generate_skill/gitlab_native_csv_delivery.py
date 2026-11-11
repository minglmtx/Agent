"""Isolated native CSV delivery draft; not an actor tool or enabled worker.

Keep native controller -> queued worker -> finder -> service -> Notify intact.
Only the final mail transport may become a local MIME spool. The Ruby observer
records actual export status without changing the CSV/body or finder parameters.
No private expected answer enters this observer. Native UI/queue correlation and
two-fresh delivery/restore tests are still required before production admission.
"""
import csv
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
import hashlib
import io
import json
import re
from urllib.parse import urlsplit

VERSION='gitlab-native-csv-local-delivery-draft-v1'
MAX_MESSAGE=32*1024*1024
MAX_CSV=15*1024*1024
KINDS={'issue':('Issue ID','issues'),'merge_request':('MR IID','merge_requests')}

# Load only in an isolated, explicitly reviewed native export worker process.
# It is a draft initializer: email-enabled/perform_deliveries settings still need
# native configuration validation, and no blanket worker is started here.
DELIVERY_ADAPTER_RUBY=r'''require 'json'
require 'digest'
require 'securerandom'
class LabNativeCsvSpool
  def initialize(settings)
    @root=File.realpath(settings.fetch(:location))
    raise 'private spool directory required' unless File.directory?(@root) && (File.stat(@root).mode & 0777)==0700
  end
  def deliver!(mail)
    context=mail.instance_variable_get(:@lab_native_csv_export)
    raise 'native export context missing' unless context.is_a?(Hash) && ['issue','merge_request'].include?(context[:type])
    payload=mail.encoded
    raise 'native MIME budget exceeded' unless payload.bytesize>0 && payload.bytesize<=32*1024*1024
    id=SecureRandom.hex(16)
    message=File.join(@root,id+'.eml');metadata=File.join(@root,id+'.json')
    File.open(message+'.tmp',File::WRONLY|File::CREAT|File::EXCL,0600){|file|file.write(payload);file.flush;file.fsync}
    context=context.merge(mime_sha256:Digest::SHA256.hexdigest(payload),version:'gitlab-native-csv-local-delivery-draft-v1')
    File.open(metadata+'.tmp',File::WRONLY|File::CREAT|File::EXCL,0600){|file|file.write(JSON.generate(context));file.flush;file.fsync}
    File.rename(message+'.tmp',message)
    File.rename(metadata+'.tmp',metadata) # JSON publishes a complete correlated pair last.
  end
end
module LabNativeCsvMailObserver
  def issues_csv_email(user,project,csv_data,status)
    value=super
    message.instance_variable_set(:@lab_native_csv_export,lab_csv_context('issue',user,project,status))
    value
  end
  def merge_requests_csv_email(user,project,csv_data,status)
    value=super
    message.instance_variable_set(:@lab_native_csv_export,lab_csv_context('merge_request',user,project,status))
    value
  end
  private
  def lab_csv_context(type,user,project,status)
    jid=ENV.fetch('LAB_NATIVE_EXPORT_JOB_ID')
    raise 'actual claimed native job ID required' unless jid.match?(/\A[0-9a-f]{24,32}\z/)
    raise 'native export status missing' unless status.is_a?(Hash)
    {type:type,worker:'IssuableExportCsvWorker',job_id:jid,user_id:user.id,project_id:project.id,project_path:project.full_path,
     rows_expected:status.fetch(:rows_expected),rows_written:status.fetch(:rows_written),truncated:status.fetch(:truncated)}
  end
end
class LabPermitNativeCsvSpoolOnly
  def self.delivering_email(message)
    context=message.instance_variable_get(:@lab_native_csv_export)
    if context.is_a?(Hash) && ['issue','merge_request'].include?(context[:type]) && message.delivery_method.is_a?(LabNativeCsvSpool)
      message.perform_deliveries=true
    end
  end
end
ActionMailer::Base.add_delivery_method(:lab_native_csv_spool,LabNativeCsvSpool,location:ENV.fetch('LAB_NATIVE_CSV_SPOOL'))
Notify.prepend(LabNativeCsvMailObserver)
Notify.delivery_method=:lab_native_csv_spool
ActionMailer::Base.register_interceptor(LabPermitNativeCsvSpoolOnly)
'''


def validate_context(context):
    if not isinstance(context,dict)or context.get('version')!=VERSION or context.get('worker')!='IssuableExportCsvWorker'or context.get('type')not in KINDS:raise ValueError('Native correlated export context required')
    for key in ('user_id','project_id'):
        if type(context.get(key))is not int or context[key]<=0:raise ValueError('Native export account/project identity missing')
    for key in ('rows_expected','rows_written'):
        if type(context.get(key))is not int or context[key]<0:raise ValueError('Native export completeness status missing')
    if type(context.get('truncated'))is not bool or not isinstance(context.get('job_id'),str)or not re.fullmatch('[0-9a-f]{24,32}',context['job_id']):raise ValueError('Native queued job/limit status missing')
    path=context.get('project_path')
    if not isinstance(path,str)or not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+',path):raise ValueError('Native project path missing')
    if not isinstance(context.get('mime_sha256'),str)or not re.fullmatch('[0-9a-f]{64}',context['mime_sha256']):raise ValueError('MIME correlation checksum missing')


def read_native_csv_message(payload,context):
    validate_context(context)
    if not isinstance(payload,bytes)or not 0<len(payload)<=MAX_MESSAGE:raise ValueError('Complete native MIME artifact required')
    if hashlib.sha256(payload).hexdigest()!=context['mime_sha256']:raise ValueError('MIME message differs from native spool receipt')
    message=BytesParser(policy=policy.default).parsebytes(payload)
    if message.defects:raise ValueError('Malformed native MIME envelope')
    recipients=[address for _,address in getaddresses(message.get_all('To',[]))]
    if len(recipients)!=1 or not recipients[0]:raise ValueError('Exact native notification recipient missing')
    parts=[part for part in message.walk()if part.get_content_disposition()=='attachment']
    if len(parts)!=1 or parts[0].get_content_type()!='text/csv':raise ValueError('Exactly one actual native CSV attachment required')
    part=parts[0];filename=part.get_filename()
    if not isinstance(filename,str)or not re.fullmatch('[A-Za-z0-9_.-]+\\.csv',filename):raise ValueError('Native CSV filename missing or unsafe')
    content=part.get_payload(decode=True)
    if part.defects or not isinstance(content,bytes)or not 0<len(content)<=MAX_CSV:raise ValueError('Decoded native CSV artifact incomplete')
    text=content.decode('utf-8-sig',errors='strict')
    if '\x00'in text:raise ValueError('Invalid CSV text')
    reader=csv.DictReader(io.StringIO(text,newline=''),strict=True);headers=reader.fieldnames
    ident,_=KINDS[context['type']]
    if(not headers or len(set(headers))!=len(headers)or any(not isinstance(h,str)or not h for h in headers)
       or not {'Title','Description',ident,'URL','State'}<=set(headers)):raise ValueError('Native export column schema missing')
    rows=list(reader)
    if any(set(row)!=set(headers)or any(not isinstance(v,str)for v in row.values())for row in rows):raise ValueError('Incomplete CSV row/column data')
    ids=[row[ident]for row in rows]
    if any(not re.fullmatch('[1-9][0-9]*',value)for value in ids)or len(set(ids))!=len(ids):raise ValueError('Native CSV record identities invalid or duplicated')
    return {'version':VERSION,'kind':context['type'],'filename':filename,'recipients':recipients,'headers':headers,'rows':rows,
            'native_context':dict(context),'csv_sha256':hashlib.sha256(content).hexdigest(),'csv_bytes':len(content),'actual_received_csv_attachment':True}



def native_text_rows_signature(rows):
    """Compare complete CSV text fields with equivalent CRLF/LF line breaks.

    Real installed native attachments contain CRLF text where independent raw
    records contain mixed LF/CRLF. Original MIME/CSV bytes and checksums remain
    untouched. Preserve every column, character, whitespace and lone CR;
    changing or removing a line break is still a different field value.
    """
    return sorted(json.dumps({key: value.replace('\r\n', '\n')
                              for key, value in row.items()}, sort_keys=True)
                  for row in rows)


def completion(received,reference):
    """Independent private full-reference check; no receipt is task success."""
    unknown=lambda reason:{'status':'unknown','reward':None,'checks':{},'reason':reason}
    if not isinstance(received,dict)or received.get('actual_received_csv_attachment')is not True:return unknown('Actual native CSV attachment not received')
    context=received.get('native_context')
    try:validate_context(context)
    except (ValueError,TypeError):return unknown('Correlated native export status missing')
    required={'type','user_id','project_id','project_path','recipient','headers','rows'}
    if not isinstance(reference,dict)or set(reference)!=required or not isinstance(reference['rows'],list)or not isinstance(reference['headers'],list):return unknown('Independent complete native export reference missing')
    if(any(type(reference.get(k))is not int or reference[k]<=0 for k in('user_id','project_id'))
       or not isinstance(reference['recipient'],str)or not reference['recipient']or '\n'in reference['recipient']
       or not isinstance(reference['project_path'],str)or not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+',reference['project_path'])
       or not reference['headers']or any(not isinstance(h,str)or not h for h in reference['headers'])or len(set(reference['headers']))!=len(reference['headers'])):return unknown('Malformed private native identity/schema reference')
    if any(not isinstance(r,dict)or set(r)!=set(reference['headers'])or any(not isinstance(v,str)for v in r.values())for r in reference['rows']):return unknown('Incomplete private reference row fields')
    kind=reference['type']
    if not isinstance(kind,str)or kind not in KINDS:return unknown('Unknown native collection reference')
    ident=KINDS[kind][0]
    if ident not in reference['headers']:return unknown('Private record identity schema missing')
    expected_ids=[r[ident]for r in reference['rows']]
    if len(set(expected_ids))!=len(expected_ids):return unknown('Private reference contains duplicate identities')
    rows=received.get('rows');headers=received.get('headers')
    if(not isinstance(rows,list)or not isinstance(headers,list)or not headers
       or any(not isinstance(h,str)or not h for h in headers)or len(set(headers))!=len(headers)
       or any(not isinstance(r,dict)or set(r)!=set(headers)or any(not isinstance(v,str)for v in r.values())for r in rows)):
        return unknown('Received native row schema missing')
    checks={'native_collection_identity':context['type']==kind,
        'native_task_account_and_recipient':context['user_id']==reference['user_id']and received.get('recipients')==[reference['recipient']],
        'native_project_identity':context['project_id']==reference['project_id']and context['project_path']==reference['project_path'],
        'native_export_not_truncated':context['truncated']is False and context['rows_expected']==context['rows_written']==len(rows)==len(reference['rows']),
        'complete_native_column_schema':headers==reference['headers'],
        'complete_exact_record_values':native_text_rows_signature(rows)==native_text_rows_signature(reference['rows'])}
    success=all(checks.values());return {'status':'success'if success else'failure','reward':float(success),'checks':checks,
        'scope':'independent complete native collection/filter reference, not queued request or copied URL'}


def native_dialog_delivery_protocol(text):
    """Only a protocol diagnostic; never completion or mail-job evidence."""
    if not isinstance(text,str):raise ValueError('Actual native dialog text required')
    lowered=text.lower()
    declared=all(word in lowered for word in('csv','background','attachment'))and('sent to'in lowered or'email'in lowered or'emailed'in lowered)
    selected=re.findall(r'\b([0-9]+)\s+(issues?|merge requests?)\s+selected\b',lowered)
    # Installed native ngettext emits singular labels only for count=1.
    # Canonical collection identifiers remain plural; this is UI protocol
    # discovery, never a CSV completion or an attachment-received signal.
    selected_count=collection=None
    if len(selected)==1:
        count,label=int(selected[0][0]),selected[0][1]
        singular=label in ('issue','merge request')
        if not singular or count==1:
            selected_count=count
            collection='issues' if label.startswith('issue') else 'merge requests'
    return {'declares_background_attachment_delivery':declared,
            'native_selected_count':selected_count,
            'native_selected_collection':collection,
            'actual_attachment_received':False,'not_a_completion_judgment':True}


def public_attachment_metadata(received):
    """Optional common download-registry event; no private oracle or body leaks."""
    if not isinstance(received,dict)or received.get('actual_received_csv_attachment')is not True:raise ValueError('Actual parsed local CSV attachment required')
    return {'kind':'csv','filename':received['filename'],'bytes':received['csv_bytes'],'sha256':received['csv_sha256'],
            'received':True,'row_count':len(received['rows']),'local_mail_delivery_adaptation':True,'task_success_not_evaluated':True}
