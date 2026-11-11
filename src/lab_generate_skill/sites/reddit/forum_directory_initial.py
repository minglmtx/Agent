"""Passive readiness from original Postmill list_all/_list_nav templates.

Original frozen SIF source receipt: forums-start-readonly-4851058.
No target forum is selected; an empty directory is still a valid initial page.
"""

FORUM_DIRECTORY_READY = """() => {
    if(location.pathname!=='/forums/all' || location.search || location.hash)return false;
    const tabs=Array.from(document.querySelectorAll('ul.unlistify.flex a.tab--active')).filter(a=>{
        const u=new URL(a.href,location.href);
        return u.origin===location.origin && u.pathname==='/forums/all' && !u.search && !u.hash;
    });
    const lists=document.querySelectorAll('div.columns.flow');
    return tabs.length===1 && !!tabs[0].getClientRects().length &&
        document.querySelectorAll('h1.page-heading').length===1 && lists.length===1 &&
        !!lists[0].getClientRects().length &&
        document.querySelectorAll('input[name="submission[image]"]').length===0;
}"""
