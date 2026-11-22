const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {execFileSync}=require('node:child_process');
const root=path.join(__dirname,'..');
const python=[process.env.PYTHON,path.join(root,'.venv/Scripts/python.exe'),path.join(root,'.venv/bin/python')]
 .find(value=>value&&fs.existsSync(value))??'python';
const config=JSON.parse(execFileSync(python,['-c',
 'import json,yaml; from pathlib import Path; data=yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8")); print(json.dumps({"triggers":data.get("on",data.get(True)),"jobs":data["jobs"]}))'],{cwd:root,encoding:'utf8'}));
const workflow=config.jobs;

// GitHub applies success() across the ancestor chain unless a status function
// overrides it: https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions
// The workflow's boolean/string comparisons use the same semantics in JS.
function releaseEligible({ref='refs/heads/main',event='push',repository='szech77/HA_EOS_Akkodoktor_Energiezentrale',
 required='success',cleanup='skipped',cancelled=false,job='publish'}={}){
 const ancestors=new Set();
 function visit(key){
  for(const name of [workflow[key].needs??[]].flat()){
   if(!ancestors.has(name)){ancestors.add(name);visit(name);}
  }
 }
 visit(job);
 const results={required,clean_changelog:cleanup};
 const success=()=>[...ancestors].every(name=>(results[name]??'success')==='success');
 const expression=workflow[job].if.trim().replace(/^\$\{\{\s*|\s*\}\}$/g,'');
 const explicitStatus=/\b(?:always|success|failure|cancelled)\s*\(/.test(expression);
 const context={github:{ref,event_name:event,repository},needs:{required:{result:required}},
  success,cancelled:()=>cancelled,always:()=>true,failure:()=>required==='failure',
  startsWith:(value,prefix)=>value.startsWith(prefix)};
 return (!explicitStatus&& !success())?false:vm.runInNewContext(expression,context);
}

test('the entire publish job waits at the release environment after required checks',()=>{
 assert.deepEqual([workflow.publish.needs].flat(),['required']);
 assert.equal(workflow.publish.environment,'release');
 assert.deepEqual(workflow.publish.permissions,{contents:'write'});
 assert.equal(workflow.publish['continue-on-error'],undefined);
 assert.ok(workflow.publish.steps.some(step=>step.name==='Build the Vue bundle from the checked source'));
 assert.ok(workflow.publish.steps.some(step=>step.run?.includes('tools/release.py publish')));
 assert.ok(config.triggers.push);
 assert.ok(config.triggers.pull_request);
 assert.ok(Object.hasOwn(config.triggers,'merge_group'));
});
test('release approval uses no issue job, issue writes or comment-polling runner',()=>{
 assert.equal(workflow.release_decision,undefined);
 for(const job of Object.values(workflow)){
  assert.equal(job.permissions?.issues,undefined);
  assert.ok(!JSON.stringify(job).includes('release_approval.py'));
 }
 // GitHub enforces the environment review before executing any of these steps;
 // this expression only decides which runs reach that review.
 assert.equal(releaseEligible(),true);
});
test('main pushes reach release approval after successful checks even when cleanup is skipped',()=>{
 assert.equal(releaseEligible(),true);
});
test('working-branch pushes reach beta approval after successful cleanup',()=>{
 for(const name of ['feature/backup-power','bug/fix','bugfix/main-release-skipped']){
  assert.equal(releaseEligible({ref:'refs/heads/'+name,cleanup:'success'}),true);
 }
});
test('failed, skipped, pending or cancelled required checks never publish',()=>{
 for(const required of ['failure','skipped','cancelled','pending'])assert.equal(releaseEligible({required}),false);
 assert.equal(releaseEligible({cancelled:true}),false);
});
test('PRs, merge groups and manual or bot dispatches never request release approval',()=>{
 for(const event of ['pull_request','merge_group','workflow_dispatch']){
  for(const ref of ['refs/heads/main','refs/heads/feature/releases'])assert.equal(releaseEligible({event,ref}),false);
 }
});
test('forks, tags and unrelated branches never request release approval',()=>{
 assert.equal(releaseEligible({repository:'someone/fork'}),false);
 for(const ref of ['refs/tags/v1.0.0','refs/heads/other'])assert.equal(releaseEligible({ref}),false);
});
