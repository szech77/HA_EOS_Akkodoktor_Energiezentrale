const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../custom_components/eos_energiezentrale/energy');
const script=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
const context={};
vm.runInNewContext(script.slice(script.indexOf('function sourceConfigurationNotice('),script.indexOf('function renderView()')),context);
const notice=context.sourceConfigurationNotice;
function translate(lang){
 const messages=JSON.parse(fs.readFileSync(path.join(root,`i18n/${lang}.json`),'utf8')).messages;
 return (key,values={})=>{
   assert.equal(typeof messages[key],'string',`Missing ${lang} translation ${key}`);
   return messages[key].replace(/\{(\w+)\}/g,(_match,name)=>values[name]??'');
 };
}
test('missing configuration names the measurement and tells users where to configure it',()=>{
 const text=notice({missing:['grid'],unavailable:[]},translate('de'));
 assert.match(text,/Konfiguration fehlt/);
 assert.match(text,/Netzanschlussleistung/);
 assert.match(text,/Quellsensoren/);
 assert.match(text,/Plugin/);
});
test('configured but unavailable sources have a different actionable notice in both languages',()=>{
 assert.match(notice({missing:[],unavailable:['grid']},translate('de')),/Keine gültigen Messwerte/);
 assert.match(notice({missing:['solar'],unavailable:['grid']},translate('en')),/Missing configuration.*PV power.*No valid measurements.*Grid connection power/);
});
test('healthy sources and older snapshots show no configuration warning',()=>{
 assert.equal(notice(undefined,translate('en')),'');
 assert.equal(notice({missing:[],unavailable:[]},translate('de')),'');
});
