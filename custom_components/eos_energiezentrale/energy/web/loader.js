/* Load one coherent UI build; the HA panel supplies its content fingerprint. */
(function(){
  'use strict';
  const version=new URL(location.href).searchParams.get('v')||String(Date.now());
  const german=(new URL(location.href).searchParams.get('lang')||navigator.language||'en').startsWith('de');
  const byId=id=>document.getElementById(id);
  const retry=byId('startup-retry');
  retry.textContent=german?'Erneut versuchen':'Retry';
  retry.addEventListener('click',()=>{
    const target=new URL(location.href);target.searchParams.set('v',String(Date.now()));location.replace(target.href);
  });
  // vue/eos-vue.js is built from frontend/ (npm run build); it is not part of the source tree.
  const bundle='vue/eos-vue.js';
  let loaded=false;
  function failed(event){
    const code=event?'ui_render_failed':'asset_mismatch';
    console.warn('EOS UI '+code);
    byId('notice').textContent=event
      ?(german?`Bei der Ausführung von ${bundle} ist ein JavaScript-Fehler aufgetreten.`:`A JavaScript error occurred while running ${bundle}.`)
      :(german?`Die Oberfläche konnte die Datei ${bundle} nicht laden. Bitte die Integration vollständig aktualisieren und erneut versuchen.`
        :`The interface could not load ${bundle}. Update the complete integration and retry.`);
    byId('startup').hidden=false;
    // A running app keeps its pages; only a failed start hides the empty mount point.
    if(!loaded)byId('app').hidden=true;
    retry.hidden=false;
    if(event){
      const details=byId('startup-details'),output=byId('startup-detail'),title=byId('startup-details-title');
      const name=['ReferenceError','TypeError','SyntaxError','RangeError','Error'].includes(event.error?.name)?event.error.name:'Error';
      output.textContent=[bundle,Number.isSafeInteger(event.lineno)?event.lineno:'',name].filter(Boolean).join(':');details.hidden=false;
      title.textContent=german?'Technische Details':'Technical details';
    }
  }
  // Parse and runtime errors of the bundle also produce a visible message, without the raw text.
  window.addEventListener('error',event=>{
    const file=String(event.filename||'').split('?')[0];
    if(file.endsWith('/'+bundle))failed(event);
  });
  const icon=document.querySelector('link[rel=icon]');if(icon)icon.href='./logo.svg?v='+encodeURIComponent(version);
  document.querySelector('link[rel=stylesheet]').href='./style.css?v='+encodeURIComponent(version);
  const script=document.createElement('script');script.src='./'+bundle+'?v='+encodeURIComponent(version);
  script.onload=()=>{loaded=true;};script.onerror=()=>failed();
  document.head.append(script);
})();
