"""Public native repository hydration signals, independent of task references.

The installed GitLab blob app replaces its mount and progressively inserts
source chunks. Its native spinner container persists through chunk rendering;
an animated spinner span can be temporarily invisible. No total line count,
file size, private Git digest, sleep or task target is used here.
"""
BLOB_SIGNALS = r'''() => {
 if(location.protocol==='chrome-error:' || !location.pathname.includes('/-/blob/'))return [];
 const shown=e=>{
   if(!e.getClientRects().length)return false;
   for(let n=e;n;n=n.parentElement){
     const style=getComputedStyle(n);
     if(style.display==='none'||style.visibility==='hidden'||style.visibility==='collapse')return false;
   }
   return true;
 };
 const holders=[...document.querySelectorAll('#blob-content-holder')].filter(shown);
 const signals=[];
 for(const holder of holders){
   // Public mount metadata identifies a still-unstarted native Vue viewer.
   if([...holder.querySelectorAll('#js-view-blob-app')].some(shown)){
     signals.push('gitlab_blob_mount_pending');continue;
   }
   // Use the enclosing native progress widget rather than opacity of its
   // animated icon. An off-screen chunk spinner still represents loading.
   if([...holder.querySelectorAll('.gl-spinner-container,[aria-busy="true"]')].some(shown)){
     signals.push('gitlab_blob_content_pending');continue;
   }
   // Primary native image viewers may mount before their same-page image request
   // completes. Inline Markdown resources are independent of complete textual hydration.
   // Deferred/broken inline images remain visible evidence and must be checked
   // by image-specific completion predicates, not block every document read.
   // A completed broken image is a terminal result, not loading.
   if([...holder.querySelectorAll('img')].filter(shown).some(image=>!image.closest('.file-content.md') && !image.complete)){
     signals.push('gitlab_blob_image_pending');continue;
   }
   // The viewer shell can briefly be present before the first content node.
   // Known native error/download/image renderers remain legitimate views;
   // they must not wait for source text that they intentionally do not show.
   if(![...holder.querySelectorAll('.file-content,.blob-viewer,[data-qa-selector="blob_viewer_file_content"],.blob-error,.blob-render-error')].some(shown))
     signals.push('gitlab_blob_viewer_pending');
 }
 return [...new Set(signals)];
}'''
