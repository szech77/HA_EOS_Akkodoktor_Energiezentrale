const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const backend=require('./backend.cjs');
const root=path.join(__dirname,'../custom_components/eos_energiezentrale/energy');
const script=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
const markupFile=fs.readFileSync(path.join(root,'web/index.html'),'utf8');
const now=Date.parse('2026-11-18T17:50:00Z'),iso=new Date(now).toISOString();

function context(code='de',extra={}){
  const language=JSON.parse(fs.readFileSync(path.join(root,`i18n/${code}.json`),'utf8'));
  const html=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const t=(key,values={})=>{assert.equal(typeof language.messages[key],'string',key);return language.messages[key].replace(/\{(\w+)\}/g,(_,name)=>values[name]??`{${name}}`);};
  const ctx={language,snapshot:{zone:'Europe/Berlin'},html,t,th:(key,values)=>html(t(key,values)),valid:Number.isFinite,Intl,Date,
    decimal:(value,digits=1)=>new Intl.NumberFormat(language.locale,{maximumFractionDigits:digits}).format(value)};
  Object.assign(ctx,extra);
  vm.createContext(ctx);
  vm.runInContext(script.slice(script.indexOf('// Numeric source diagnostics'),script.indexOf('function settings()')),ctx);
  return ctx;
}
const render=(view,code='de')=>context(code).sourceDiagnostics(view);
const plugin={type:'plugin',name:'Configured devices'};
const data={live:{time:iso,solar:0,grid:10,house_total:940,house:940,heat:0,car:0,battery_soc:87,battery_charge:0,battery_discharge:510},
  features:{car:true,heat:true},
  plugins:{battery:{name:'Configured devices',measurements:['battery_soc','battery_charge','battery_discharge']},wallbox:{name:'go-e <v2>',measurements:['car']}},
  source_configuration:{missing:[],unavailable:['heat'],sources:{
    solar:{source:plugin,available:true,reason:null,max_age_s:45,sample:iso},
    grid:{source:plugin,available:true,reason:null,max_age_s:45,sample:iso},
    house_total:{source:plugin,available:true,reason:null,max_age_s:120,sample:iso},
    heat:{source:{type:'sensor',name:'sensor.heat_pump'},available:false,reason:'stale',max_age_s:120,sample:new Date(now-300000).toISOString()}}},
  battery_group:{devices:[{name:'Victron',battery:true,available:true,plugin:{name:'Victron GX'},soc:87,charge:0,discharge:510,measurements:{grid:10,house_total:940}}]}};

test('settings show every configured source with numeric values, age and status',()=>{
  const view=backend('sourceDiagnostics',data,{now});
  const markup=render(view);
  assert.match(markup,/<td>Netzanschlussleistung<\/td><td>Plugin: Configured devices<\/td><td class="num">10 W<\/td><td class="num">0 s<\/td><td>OK<\/td>/);
  assert.match(markup,/<tr class="warn"><td>Wärmepumpenleistung<\/td><td>Sensor: <code>sensor\.heat_pump<\/code><\/td><td class="num">—<\/td><td class="num">300 s<\/td><td>veraltet \(max\. 120 s\)<\/td>/);
  assert.match(markup,/Speicher-Entladeleistung<\/td><td>Plugin: Configured devices<\/td><td class="num">510 W/);
  assert.match(markup,/Plugin: go-e &lt;v2&gt;/);assert.doesNotMatch(markup,/<v2>/);
  assert.match(markup,/Stand 18:50:00/);
});
test('the AC balance replaces a deviating measured house total and says so',()=>{
  const markup=render(backend('balancedDiagnostics',data,{now}));
  assert.match(markup,/Hausverbrauch gesamt aus Bilanz \(PV \+ Netz \+ Entladung − Ladung\)<\/td><td class="num">520 W/);
  assert.match(markup,/Hausverbrauch gesamt gemessen \(Kontrolle\)<\/td><td class="num">940 W/);
  assert.match(markup,/Abweichung: Bilanz − Messung<\/strong><\/td><td class="num">−420 W/);
  assert.match(markup,/<tr class="warn"><td colspan="2"><strong>Gemessener Hausverbrauch weicht ab/);
  assert.match(markup,/<h3>Victron · Victron GX<\/h3>/);assert.match(markup,/Speicher-SoC<\/td><td class="num">87 %/);
  const balanced=render(backend('balancedDiagnostics',{...data,live:{...data.live,house_total:500,house:500}},{now}),'en');
  assert.match(balanced,/<tr class=""><td colspan="2"><strong>Measurement matches the balance/);
});
test('estimated values are listed with their reason',()=>{
  const markup=render(backend('sourceDiagnostics',{...data,live:{...data.live,balance:{house_total:520,complete:true,
    consumers:{house:520,car:0,heat:0},estimated:{heat:'consumer_hold',solar:'source_balance'}}}},{now}));
  assert.match(markup,/<h3>Geschätzte Werte in diesem Moment<\/h3>/);
  assert.match(markup,/<td>PV-Leistung<\/td><td>aus gemessenem Hausverbrauch und den übrigen Quellen berechnet<\/td>/);
  assert.match(markup,/<td>Wärmepumpenleistung<\/td><td>Messwert kurz nicht verfügbar, letzter Wert gehalten<\/td>/);
});
test('no diagnostics yet and the settings panel exists',()=>{
  assert.match(render(undefined),/Noch keine Messwerte/);
  // The diagnostics sit in the System section of the settings.
  assert.match(markupFile,/<section data-settings-section="system" hidden>[\s\S]*?<details id="source-diagnostics-panel"><summary data-i18n="diagnostics.title"><\/summary>[\s\S]*?<\/section>/);
});

test('copy puts an aligned plain-text report into the clipboard',async()=>{
  const view=backend('balancedDiagnostics',data,{now}),result={textContent:''};let copied;
  const ctx=context('de',{byId:()=>result,navigator:{clipboard:{writeText:async text=>{copied=text;}}}});
  ctx.snapshot.source_diagnostics=view;
  await ctx.copyDiagnostics();
  assert.equal(result.textContent,'Messwerte in die Zwischenablage kopiert.');
  const lines=copied.split('\n');
  assert.equal(lines[0],'EOS Energiezentrale · Diagnose · Messquellen');
  assert.match(lines[1],/^Stand 18\.11\.26, 18:50:00 \(2026-11-18T17:50:00/);
  assert.ok(lines.some(line=>/^Netzanschlussleistung +Plugin: Configured devices +10 W +0 s +OK$/.test(line)));
  assert.ok(lines.some(line=>/^Wärmepumpenleistung +Sensor: sensor\.heat_pump +— +300 s +veraltet \(max\. 120 s\)$/.test(line)));
  assert.match(copied,/Abweichung: Bilanz − Messung +-420 W\nErlaubte Abweichung +300 W\nGemessener Hausverbrauch weicht ab/);
  assert.ok(lines.includes('Geräte: Victron · Victron GX · Messwerte vollständig'));
  assert.match(copied,/Speicher-Entladeleistung +510 W/);
  // Plain text keeps names unescaped.
  assert.match(copied,/Plugin: go-e <v2>/);assert.doesNotMatch(copied,/&lt;|&amp;/);
  // Right-aligned value and age columns end below their headings in every source row.
  const header=lines.find(line=>line.startsWith('Messgröße'));
  const rows=lines.slice(lines.indexOf(header)+1,lines.indexOf(header)+1+view.sources.length);
  const valueEnd=header.indexOf('Wert')+4,ageEnd=header.indexOf('Alter')+5;
  assert.equal(rows.length,8);
  rows.forEach(line=>{assert.match(line.slice(0,valueEnd),/(W|%|—)$/,line);assert.match(line.slice(0,ageEnd),/( s|—)$/,line);});
});
test('copy falls back to a selected text area and reports a blocked clipboard',async()=>{
  const result={textContent:''},appended=[];
  const area={style:{},setAttribute(){},select(){},remove(){}};
  const document={createElement:()=>area,body:{append:item=>appended.push(item)},execCommand:()=>true};
  const ctx=context('en',{byId:()=>result,document,navigator:{clipboard:{writeText:async()=>{throw new Error('denied');}}}});
  ctx.snapshot.source_diagnostics=backend('balancedDiagnostics',data,{now});
  await ctx.copyDiagnostics();
  assert.equal(result.textContent,'Measurements copied to the clipboard.');assert.match(area.value,/Measured house consumption deviates/);
  document.execCommand=()=>false;await ctx.copyDiagnostics();
  assert.match(result.textContent,/Copying is not possible/);
});
test('export downloads a dated UTF-8 text file with the same report',async()=>{
  const result={textContent:''},link={click(){this.clicked=true;},remove(){}};let blob;
  const ctx=context('de',{byId:()=>result,document:{createElement:()=>link,body:{append(){}}},
    URL:{createObjectURL:value=>{blob=value;return 'blob:x';},revokeObjectURL(){}},Blob,setTimeout:()=>{}});
  ctx.snapshot.source_diagnostics=backend('sourceDiagnostics',data,{now});
  ctx.exportDiagnostics();
  assert.equal(link.download,'eos-messwerte-2026-11-18-17-50-00.txt');assert.equal(link.clicked,true);
  assert.equal(blob.type,'text/plain;charset=utf-8');assert.match(await blob.text(),/Speicher-Entladeleistung +510 W/);
  assert.equal(result.textContent,'Datei eos-messwerte-2026-11-18-17-50-00.txt gespeichert.');
  assert.match(markupFile,/id="diagnostics-copy" data-i18n="diagnostics.copy"/);assert.match(markupFile,/id="diagnostics-export" data-i18n="diagnostics.export"/);
});
