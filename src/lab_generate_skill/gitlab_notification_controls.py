"""Scoped public metadata for GitLab's native notification dropdown.

The mount/class and attributes are from the installed native _home_panel HAML.
This reader neither changes notification settings nor exposes a target answer.
"""
READ=r'''() => {
 const shown=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 return [...document.querySelectorAll('.js-vue-notification-dropdown')].filter(shown).map(e=>({
   project_id:e.getAttribute('data-project-id'),
   notification_level:e.getAttribute('data-notification-level'),
   disabled:e.getAttribute('data-disabled'),
   dropdown_items:e.getAttribute('data-dropdown-items'),
   buttons:[...e.querySelectorAll('button')].filter(shown).map(b=>({
     id:b.id,classes:b.className,text:b.innerText,label:b.getAttribute('aria-label'),
     title:b.getAttribute('title'),expanded:b.getAttribute('aria-expanded')
   }))
 }));
}'''
