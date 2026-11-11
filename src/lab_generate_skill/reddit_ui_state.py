"""Terminal-only native UI states; no saved-content or semantic-writing claim."""
from urllib.parse import urlsplit


def validate(spec):
    if spec.get('kind') == 'image_submission':
        if set(spec) != {'kind'}:
            raise ValueError('Unexpected image-tab fields')
    elif spec.get('kind') == 'account_menu':
        if set(spec) != {'kind', 'username'} or not isinstance(spec['username'], str) or not spec['username']:
            raise ValueError('Missing account identity')
    elif spec.get('kind')=='comment_formatting_help':
        rows=spec.get('rows')
        if (set(spec)!={'kind','rows'}or not isinstance(rows,list)or not rows
            or any(not isinstance(r,list)or len(r)!=2 or any(not isinstance(x,str)or not x.strip()for x in r)for r in rows)):
            raise ValueError('Pinned native formatting table required')
    else:
        raise ValueError('Unsupported Reddit UI state')


def read_ui_state(page):
    return page.evaluate(r'''() => {
      const visible=e=>!!e && !!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
      const forms=[...document.forms].filter(f=>f.querySelector('#submission_mediaType_image')).map(f=>({
        image_selected:f.querySelector('#submission_mediaType_image')?.checked===true,
        url_selected:f.querySelector('#submission_mediaType_url')?.checked===true,
        image_visible:visible(f.querySelector('#submission_image')),
        url_visible:visible(f.querySelector('#submission_url')),
        title_visible:visible(f.querySelector('#submission_title')),
        body_visible:visible(f.querySelector('#submission_body'))
      }));
      // Native Postmill can expose a link with role=button and haspopup=true.
      // Both true and menu denote a menu; use the actual accessible control,
      // not only HTML button elements with one spelling of the attribute.
      const menus=[...document.querySelectorAll('[aria-haspopup]')].filter(b=>visible(b) &&
        (b.tagName==='BUTTON'||b.getAttribute('role')==='button') &&
        ['true','menu'].includes(b.getAttribute('aria-haspopup'))).map(b=>{
        const name=b.innerText.trim(),prefix='/user/'+encodeURIComponent(name);
        let container=b.parentElement;
        // Read the nearest native container holding this account's menu links,
        // including hidden links when locating it; only visible links are scored.
        while(container && container!==document.body){
          const links=[...container.querySelectorAll('a[href]')];
          if(links.some(a=>a.getAttribute('href')===prefix+'/preferences'))break;
          container=container.parentElement;
        }
        const links=container && container!==document.body ? [...container.querySelectorAll('a[href]')].filter(visible):[];
        return {name,element_tag:b.tagName,popup_type:b.getAttribute('aria-haspopup'),
          expanded:b.getAttribute('aria-expanded'),links:links.map(a=>({text:a.innerText.trim(),href:a.getAttribute('href')}))};
      });
      const help_tables=[...document.querySelectorAll('table.formatting-help')].map(t=>{
        const form=t.closest('form'),box=t.parentElement.querySelector('input[type=checkbox]');
        const comment=form?.querySelector('textarea[name^="reply_to_submission_"][name$="[comment]"]');
        return {comment_form:visible(comment),visible:visible(t),checked:box?.checked===true,
          rows:[...t.querySelectorAll('tr')].map(r=>[...r.querySelectorAll('td')].map(c=>c.innerText.trim()))};
      });
      return {forms,menus,help_tables};
    }''')


def checks(spec,state):
    validate(spec)
    if not isinstance(state,dict) or not isinstance(state.get('forms'),list) or not isinstance(state.get('menus'),list):
        raise ValueError('Missing native UI capture')
    if spec['kind']=='image_submission':
        rows=state['forms']
        ok=len(rows)==1 and all(rows[0].get(k) is True for k in ('image_selected','image_visible','title_visible','body_visible')) and all(rows[0].get(k) is False for k in ('url_selected','url_visible'))
        return {'image_submission_tab_active':ok}
    if spec['kind']=='comment_formatting_help':
        if not isinstance(state.get('help_tables'),list):raise ValueError('Missing native help table capture')
        expected=[[' '.join(x.split())for x in r]for r in spec['rows']]
        matching=[]
        for r in state['help_tables']:
            if not isinstance(r,dict)or not isinstance(r.get('rows'),list):raise ValueError('Malformed help table capture')
            if any(not isinstance(row,list)or any(not isinstance(x,str)for x in row)for row in r['rows']):raise ValueError('Malformed help cells')
            matching.append(r.get('comment_form')is True and r.get('visible')is True and r.get('checked')is True
                and [[' '.join(x.split())for x in row]for row in r['rows']]==expected)
        return {'comment_formatting_help_visible':any(matching)}
    rows=[r for r in state['menus'] if r.get('name')==spec['username']]
    prefix='/user/'+spec['username']
    links=[] if len(rows)!=1 else rows[0].get('links',[])
    # Native menu links are local relative routes, not similarly named external URLs.
    paths=[r.get('href') for r in links if isinstance(r.get('href'),str) and not urlsplit(r['href']).netloc]
    return {'account_menu_expanded':len(rows)==1 and rows[0].get('expanded')=='true',
            'account_menu_items_visible':all(paths.count(p)==1 for p in (prefix,prefix+'/account',prefix+'/preferences'))}


def set_control(page,spec,opened=True):
    """CPU controls only. Never called by the actor or at terminal capture."""
    validate(spec)
    if spec['kind']=='image_submission':
        page.locator('label[for="submission_mediaType_'+('image' if opened else 'url')+'"]').click()
    elif spec['kind']=='comment_formatting_help':
        forms=page.locator('form').filter(has=page.locator('textarea[name^="reply_to_submission_"][name$="[comment]"]:visible'))
        if forms.count()!=1:raise ValueError('Comment form ambiguous in control fixture')
        box=forms.locator('input[id$="_comment_markdown_help"]')
        if box.count()!=1:raise ValueError('Comment help checkbox missing')
        if box.is_checked()!=opened:
            import json
            forms.locator('label[for='+json.dumps(box.get_attribute('id'))+']').click()
    else:
        button=page.get_by_role('button',name=spec['username'],exact=True)
        if button.count()!=1:raise ValueError('Account menu button missing or ambiguous')
        if (button.get_attribute('aria-expanded')=='true') != opened:button.click()


FEEDBACK={'image_submission_tab_active':'The image submission tab and its native input are active.',
          'comment_formatting_help_visible':'A comment form has its complete native formatting help table visibly expanded.',
          'account_menu_expanded':'The current account menu is expanded.',
          'account_menu_items_visible':'The current account menu entries are visible.'}
