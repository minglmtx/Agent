"""Read-only OpenRouter credit checks and explicit, approximate request estimates."""
from datetime import datetime,timezone
import json
import math
import os

from .schemas import CompactSkill

class BudgetPause(RuntimeError):
    def __init__(self,reason,details=None):
        self.reason=reason;self.details=details or {}
        super().__init__(reason)


def number(value):
    if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value):return float(value)
    return None


def read_json(endpoint,*,key=None,optional=False):
    import requests
    headers={'Authorization':'Bearer '+key} if key else {}
    try:
        r=requests.get('https://openrouter.ai/api/v1/'+endpoint,headers=headers,timeout=30)
        if optional and r.status_code in (401,403):return None
        r.raise_for_status()
        return r.json()['data']
    except (requests.RequestException,ValueError,KeyError):
        raise BudgetPause('credit_or_catalog_check_failed',{'endpoint':endpoint}) from None


def credit_snapshot():
    key=os.environ.get('OPENROUTER_API_KEY')
    if not key:raise BudgetPause('missing_api_key')
    info=read_json('key',key=key)
    account=read_json('credits',key=key,optional=True)
    key_remaining=number(info.get('limit_remaining'))
    account_remaining=None
    if account is not None:
        total=number(account.get('total_credits'));used=number(account.get('total_usage'))
        if total is not None and used is not None:account_remaining=total-used
    values=[v for v in (key_remaining,account_remaining) if v is not None]
    if not values:raise BudgetPause('available_credit_unknown')
    return {'checked_at':datetime.now(timezone.utc).isoformat(),
            'key_remaining_usd':key_remaining,'account_remaining_usd':account_remaining,
            'available_usd':max(0.,min(values)),
            'key_usage_usd':number(info.get('usage')),
            'account_balance_verified':account_remaining is not None}


def model_catalog(model):
    match=next((r for r in read_json('models') if r['id']==model),None)
    if match is None:raise BudgetPause('teacher_model_not_in_catalog')
    return {'id':model,'pricing':match['pricing'],'context_length':match['context_length'],
            'checked_at':datetime.now(timezone.utc).isoformat()}


def estimate_request(messages,max_output_tokens,catalog,*,input_tokens=None):
    if input_tokens is None:
        import tiktoken
        enc=tiktoken.get_encoding('o200k_base')
        payload=json.dumps({'messages':messages,'response_schema':CompactSkill.model_json_schema()},ensure_ascii=False)
        input_tokens=len(enc.encode(payload,disallowed_special=()))+64
    # Tokenizer/template and routing differences mean this is not a billing quote.
    reserved_input=math.ceil(input_tokens*1.25)+256
    pricing=catalog['pricing'];rates=[pricing]
    for tier in pricing.get('overrides',[]):
        if int(tier.get('min_prompt_tokens',0))<=reserved_input:rates.append(tier)
    def rate(fields):
        values=[float(r[k]) for r in rates for k in fields if k in r]
        if not values or any(not math.isfinite(x) or x<0 for x in values):raise BudgetPause('invalid_catalog_prices')
        return max(values)
    pin=rate(['prompt','input_cache_write']);pout=rate(['completion'])
    request=max([float(r.get('request',0)) for r in rates])
    amount=(reserved_input*pin+max_output_tokens*pout+request)*1.10
    return {'approx_input_tokens':input_tokens,'reserved_input_tokens':reserved_input,
            'max_output_tokens':max_output_tokens,'input_usd_per_token':pin,'output_usd_per_token':pout,
            'reserve_usd':round(amount,6),'context_fits':reserved_input+max_output_tokens<=catalog['context_length'],
            'note':'Planning estimate, o200k_base + input/output-cost margins; not a guaranteed bill cap.'}


class CreditGuard:
    def __init__(self,catalog,read_balance=credit_snapshot):
        self.catalog=catalog;self.read_balance=read_balance

    def check(self,messages,backend,spent,budget):
        estimate=estimate_request(messages,backend.settings.max_new_tokens,self.catalog)
        if not estimate['context_fits']:raise BudgetPause('teacher_context_too_large',{'estimate':estimate})
        balance=self.read_balance()
        details={'estimate':estimate,'balance':balance,'reported_cost_usd':spent,'budget_usd':budget}
        if spent+estimate['reserve_usd']>budget:raise BudgetPause('next_request_exceeds_run_budget',details)
        if estimate['reserve_usd']>balance['available_usd']:raise BudgetPause('insufficient_available_credit',details)
        return details
