"""Preserve native checkbox semantics when its own visible label covers the input."""
import ast
import inspect


def native_checkbox_click(bid, button='left', modifiers=None):
    """Injected after BrowserGym helpers; never forces a click or selects a value."""
    modifiers=[] if modifiers is None else modifiers
    elem=get_elem_by_bid(page,bid,demo_mode != 'off')
    label_bid=elem.evaluate('''e => {
      if(e.tagName!=="INPUT" || !["checkbox","radio"].includes(e.type) || e.disabled
          || e.getAttribute("aria-disabled")==="true") return null;
      const r=e.getBoundingClientRect();
      if(r.width<=0 || r.height<=0) return null;
      const hit=e.ownerDocument.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
      if(!hit || hit===e || e.contains(hit)) return null;
      const labels=[...(e.labels||[])].filter(l=>l.control===e);
      // Never substitute a different control or bypass a loading/modal overlay.
      // Styled native controls may place their own sibling button over the
      // input's centre while leaving the exact associated label clickable.
      // A native input may have both a field-name label and a styled switch
      // label. Select the label actually covering this input, not an arbitrary
      // label or an unrelated control. Ambiguous covering labels stay rejected.
      const covering=labels.filter(l=>l===hit || l.contains(hit));
      const candidates=covering.length?covering:labels.filter(l=>
        hit.tagName==="BUTTON" && hit.parentElement===e.parentElement
        && l.parentElement===e.parentElement);
      if(candidates.length!==1) return null;
      const label=candidates[0],lr=label.getBoundingClientRect();
      if(lr.width<=0 || lr.height<=0) return null;
      const labelHit=e.ownerDocument.elementFromPoint(lr.x+lr.width/2,lr.y+lr.height/2);
      if(!labelHit || !(labelHit===label || label.contains(labelHit))) return null;
      const hitOwnLabel=(label===hit || label.contains(hit));
      const siblingButton=(hit.tagName==="BUTTON" && hit.parentElement===e.parentElement
                           && label.parentElement===e.parentElement);
      if(!hitOwnLabel && !siblingButton) return null;
      // A link/button nested inside a label has its own activation semantics.
      if(labelHit.closest("a,button,input,select,textarea") && labelHit!==e) return null;
      return label.getAttribute("bid");
    }''') if button=='left' and not modifiers else None
    target=get_elem_by_bid(page,label_bid,demo_mode != 'off') if label_bid else elem
    add_demo_mode_effects(page,target,label_bid or bid,demo_mode=demo_mode,move_cursor=True)
    target.click(button=button,modifiers=modifiers,force=False,timeout=500)


def native_category_position_fill(bid, value, enable_autocomplete_menu=False):
    """Keep the selected native legacy field's keyboard-driven form value in sync."""
    elem=get_elem_by_bid(page,bid,demo_mode != 'off')
    legacy=elem.evaluate('''e => e.tagName === "INPUT" && e.name === "position"
      && !!e.closest("#catalog_category_products_table") && !e.disabled
      && !!e.checkboxElement && e.checkboxElement.checked === true
      && e.checkboxElement.positionElement === e''')
    if not legacy:
        return original_browsergym_fill(bid,value,enable_autocomplete_menu)
    # BrowserGym's existing hybrid entry types the final character with real
    # keyboard events. It does not select another product or prescribe a value.
    original_browsergym_fill(bid,value,True)
    if value == '':
        elem.press('Backspace',timeout=500)


def action_mapping(action_set, milliseconds=500):
    """Apply to the execution interface for every task, not task-specific strategy."""
    if type(milliseconds) is not int or not 500<=milliseconds<=10000:
        raise ValueError('Native control deadline must be 500..10000 ms')
    implementation=inspect.getsource(native_checkbox_click).replace('timeout=500)',f'timeout={milliseconds})')
    fill_implementation=inspect.getsource(native_category_position_fill).replace('timeout=500)',f'timeout={milliseconds})')
    def map_action(action):
        code=action_set.to_python_code(action)
        tree=ast.parse(code)
        node=tree.body[-1]
        if (isinstance(node,ast.Expr) and isinstance(node.value,ast.Call)
                and isinstance(node.value.func,ast.Name) and node.value.func.id=='fill'):
            prefix='\n'.join(code.splitlines()[:node.lineno-1])+'\n'
            return prefix+'original_browsergym_fill = fill\n'+fill_implementation+'\nfill = native_category_position_fill\n'+ast.unparse(node)+'\n'
        if (not isinstance(node,ast.Expr) or not isinstance(node.value,ast.Call)
                or not isinstance(node.value.func,ast.Name) or node.value.func.id!='click'):
            return code
        prefix='\n'.join(code.splitlines()[:node.lineno-1])+'\n'
        return prefix+implementation+'\nclick = native_checkbox_click\n'+ast.unparse(node)+'\n'
    return map_action
