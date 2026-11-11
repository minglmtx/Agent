"""Read-only DOM diagnostics for checkbox pointer interception. No task data lookup."""
import ast


def click_target(page, action):
    try:
        call=ast.parse(action,mode='eval').body
        if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Name) or call.func.id!='click':return None
        bid=ast.literal_eval(call.args[0])
    except (SyntaxError,ValueError,IndexError):return None
    return page.evaluate('''bid => {
      const all=[...document.querySelectorAll('[bid]')].filter(e=>e.getAttribute('bid')===bid);
      if(all.length!==1)return {available:false, matches:all.length};
      const e=all[0], r=e.getBoundingClientRect(), hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
      const labels=[...(e.labels||[])];
      const label=labels.find(l=>l===hit || l.contains(hit));
      const describe=x=> {
        if(!x)return null;
        const rect=x.getBoundingClientRect(),style=getComputedStyle(x);
        const centerHit=document.elementFromPoint(rect.x+rect.width/2,rect.y+rect.height/2);
        return {tag:x.tagName,id:x.id,classes:x.className,bid:x.getAttribute('bid'),
          rect:{x:rect.x,y:rect.y,width:rect.width,height:rect.height},
          style:{display:style.display,visibility:style.visibility,opacity:style.opacity,
                 clip:style.clip,clipPath:style.clipPath,pointerEvents:style.pointerEvents},
          center_hit:centerHit?{tag:centerHit.tagName,bid:centerHit.getAttribute('bid')}:null,
          center_inside:!!centerHit&&(centerHit===x||x.contains(centerHit))};
      };
      return {available:true,target:describe(e),hit:describe(hit),type:e.type,
        checked:e.checked,disabled:e.disabled,aria_disabled:e.getAttribute('aria-disabled'),
        associated_labels:labels.map(describe),hit_is_associated_label:!!label,
        safe_label_bid:label && label.getAttribute('bid'),
        label_for:label && label.htmlFor,
        viewport:{width:innerWidth,height:innerHeight,scrollX,scrollY},
        visible:r.width>0&&r.height>0,center:{x:r.x+r.width/2,y:r.y+r.height/2}};
    }''',bid)
