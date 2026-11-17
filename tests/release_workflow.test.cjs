const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {execFileSync}=require('node:child_process');
const root=path.join(__dirname,'..');
const python=[process.env.PYTHON,path.join(root,'.venv/Scripts/python.exe'),path.join(root,'.venv/bin/python')]
 .find(value=>value&&fs.existsSync(value))??'python';
const workflow=JSON.parse(execFileSync(python,['-c',
 'import json,yaml; from pathlib import Path; print(json.dumps(yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))["jobs"]))'],{cwd:root,encoding:'utf8'}));

// GitHub applies success() across the ancestor chain unless a status function
// overrides it: https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions
// The workflow's boolean/string comparisons use the same semantics in JS.
function publish({ref='refs/heads/main',event='push',repository='szech77/HA_EOS_Akkodoktor_Energiezentrale',
 required='success',cleanup='skipped',cancelled=false}={}){
 const ancestors=new Set();
 function visit(key){
  for(const name of [workflow[key].needs??[]].flat()){
   if(!ancestors.has(name)){ancestors.add(name);visit(name);}
  }
 }
 visit('publish');
 const results={required,clean_changelog:cleanup};
 const success=()=>[...ancestors].every(name=>(results[name]??'success')==='success');
 const expression=workflow.publish.if.trim().replace(/^\$\{\{\s*|\s*\}\}$/g,'');
 const explicitStatus=/\b(?:always|success|failure|cancelled)\s*\(/.test(expression);
 const context={github:{ref,event_name:event,repository},needs:{required:{result:required}},
  success,cancelled:()=>cancelled,always:()=>true,failure:()=>required==='failure',
  startsWith:(value,prefix)=>value.startsWith(prefix)};
 return (!explicitStatus&& !success())?false:vm.runInNewContext(expression,context);
}

test('main publishes after successful required checks even when branch cleanup is skipped',()=>{
 assert.equal(publish(),true);
});
test('working branches still publish betas after successful cleanup',()=>{
 for(const name of ['feature/backup-power','bug/fix','bugfix/main-release-skipped']){
  assert.equal(publish({ref:'refs/heads/'+name,cleanup:'success'}),true);
 }
});
test('failed, skipped, pending or cancelled required checks never publish',()=>{
 for(const required of ['failure','skipped','cancelled','pending'])assert.equal(publish({required}),false);
 assert.equal(publish({cancelled:true}),false);
});
test('PRs, manual runs, other repositories, tags and unrelated branches never publish',()=>{
 for(const event of ['pull_request','workflow_dispatch','merge_group'])assert.equal(publish({event}),false);
 assert.equal(publish({repository:'someone/fork'}),false);
 for(const ref of ['refs/tags/v1.0.0','refs/heads/other'])assert.equal(publish({ref}),false);
});
