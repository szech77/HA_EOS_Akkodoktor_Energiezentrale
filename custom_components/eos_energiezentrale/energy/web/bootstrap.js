/* Load one coherent UI build; the HA panel supplies its content fingerprint. */
(function(){
  'use strict';
  const version=new URL(location.href).searchParams.get('v')||String(Date.now());
  const retry=document.getElementById('startup-retry');
  const german=(new URL(location.href).searchParams.get('lang')||navigator.language).startsWith('de');
  retry.textContent=german?'Erneut versuchen':'Retry';
  retry.addEventListener('click',()=>{
    const target=new URL(location.href);target.searchParams.set('v',String(Date.now()));location.replace(target.href);
  });
  function failed(file){
    document.getElementById('notice').textContent=german
      ?`Die Oberfläche konnte die Datei ${file} nicht laden. Bitte die Integration vollständig aktualisieren und erneut versuchen.`
      :`The interface could not load ${file}. Update the complete integration and retry.`;
    document.getElementById('overview').hidden=true;retry.hidden=false;
  }
  const known=['chart-data.js','accounting.js','forecast.js','app.js'];
  // Parse/runtime errors before app startup must also produce a visible message.
  window.addEventListener('error',event=>{
    const file=String(event.filename||'').split('/').pop().split('?')[0];
    if(known.includes(file))failed(file);
  });
  for(const use of document.querySelectorAll('use[data-logo]'))use.setAttribute('href','./logo.svg?v='+encodeURIComponent(version)+'#mark');
  const icon=document.querySelector('link[rel=icon]');if(icon)icon.href='./logo.svg?v='+encodeURIComponent(version);
  document.querySelector('link[rel=stylesheet]').href='./style.css?v='+encodeURIComponent(version);
  async function load(){
    for(const file of known){
      await new Promise((resolve,reject)=>{
        const script=document.createElement('script');script.src='./'+file+'?v='+encodeURIComponent(version);
        script.onload=resolve;script.onerror=()=>{failed(file);reject(Error('UI asset unavailable'));};
        document.head.append(script);
      });
    }
  }
  load().catch(()=>{}); // The failing asset has already been named in the UI.
})();
