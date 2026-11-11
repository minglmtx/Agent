"""Current public-profile identity from its own native header, not project cards."""
import re
from urllib.parse import urlsplit,unquote

READ = r'''() => {
 const shown=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const headers=[...document.querySelectorAll('.user-profile > .cover-block > .profile-header,.user-profile .profile-header')].filter(shown);
 return {url:location.href,body_page:document.body.getAttribute('data-page'),headers:headers.map(h=>({
   names:[...h.querySelectorAll('.user-info h1.cover-title[itemprop="name"]')].filter(shown).map(e=>e.innerText.trim()),
   username_labels:[...h.querySelectorAll('.user-info .middle-dot-divider')].filter(shown).map(e=>e.innerText.trim()).filter(s=>/^@[A-Za-z0-9_.-]+$/.test(s)),
   copy_user_ids:[...h.querySelectorAll('button[data-clipboard-text]')].filter(e=>shown(e)&&(e.getAttribute('aria-label')==='Copy user ID'||e.getAttribute('title')==='Copy user ID')).map(e=>({
      id:e.getAttribute('data-clipboard-text'),label:e.parentElement.innerText.trim()}))
 }))};
}'''


def read_profile_identity(page):
    return page.evaluate(READ)


def profile_identity(state):
    if not isinstance(state,dict)or not isinstance(state.get('url'),str)or state.get('body_page')!='users:show':
        raise ValueError('Native public user profile required')
    headers=state.get('headers')
    if not isinstance(headers,list)or len(headers)!=1:raise ValueError('Current native profile header absent or ambiguous')
    header=headers[0];names=header.get('names');labels=header.get('username_labels');copies=header.get('copy_user_ids')
    if (not isinstance(names,list)or len(names)!=1 or not isinstance(names[0],str)or not names[0].strip()
            or not isinstance(labels,list)or len(labels)!=1 or not re.fullmatch('@[A-Za-z0-9_.-]+',labels[0])
            or not isinstance(copies,list)or len(copies)!=1):raise ValueError('Native header identity fields absent or ambiguous')
    row=copies[0]
    if (not isinstance(row,dict)or not isinstance(row.get('id'),str)or not re.fullmatch('[1-9][0-9]*',row['id'])
            or row.get('label')!='User ID: '+row['id']):raise ValueError('Native Copy user ID disagrees with its visible label')
    username=labels[0][1:];path=unquote(urlsplit(state['url']).path).rstrip('/')
    if path!='/'+username:raise ValueError('Native current profile route and header disagree')
    return {'user_id':int(row['id']),'username':username,'name':names[0].strip()}


def profile_checks(spec,state):
    expected=spec.get('owner_id');username=spec.get('owner_username');name=spec.get('owner_name')
    if type(expected)is not int or expected<=0 or not isinstance(username,str)or not username or not isinstance(name,str)or not name:
        raise ValueError('Explicit native user-namespace reference required')
    identity=profile_identity(state)
    return {'current_profile_user_identity':identity['user_id']==expected,
            'current_profile_username':identity['username']==username,
            'current_profile_name':identity['name']==name}
