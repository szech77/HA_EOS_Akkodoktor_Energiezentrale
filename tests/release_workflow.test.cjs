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
 required='success',cleanup='skipped',cancelled=false,job='publish',approval='true',decisionResult='success'}={}){
 const ancestors=new Set();
 function visit(key){
  for(const name of [workflow[key].needs??[]].flat()){
   if(!ancestors.has(name)){ancestors.add(name);visit(name);}
  }
 }
 visit(job);
 const results={required,clean_changelog:cleanup,release_decision:decisionResult};
 const success=()=>[...ancestors].every(name=>(results[name]??'success')==='success');
 const expression=workflow[job].if.trim().replace(/^\$\{\{\s*|\s*\}\}$/g,'');
 const explicitStatus=/\b(?:always|success|failure|cancelled)\s*\(/.test(expression);
 const context={github:{ref,event_name:event,repository},needs:{required:{result:required},
  release_decision:{result:decisionResult,outputs:{approved:approval}}},
  success,cancelled:()=>cancelled,always:()=>true,failure:()=>required==='failure',
  startsWith:(value,prefix)=>value.startsWith(prefix)};
 return (!explicitStatus&& !success())?false:vm.runInNewContext(expression,context);
}

test('issue decisions wait for required checks and publish requires both success and approval',()=>{
 assert.deepEqual([workflow.release_decision.needs].flat(),['required']);
 assert.deepEqual(workflow.publish.needs,['required','release_decision']);
 assert.deepEqual(workflow.release_decision.permissions,{contents:'read',issues:'write'});
 assert.deepEqual(workflow.publish.permissions,{contents:'write'});
 assert.equal(workflow.publish.environment,undefined);
 assert.equal(workflow.release_decision['continue-on-error'],undefined);
 assert.equal(workflow.publish['continue-on-error'],undefined);
 assert.ok(config.triggers.push);
 assert.ok(config.triggers.pull_request);
 assert.ok(Object.hasOwn(config.triggers,'merge_group'));
});
test('a successful no, closed request or timeout skips publication without an error job',()=>{
 for(const approval of ['false','','TRUE','approved'])assert.equal(releaseEligible({approval}),false);
 assert.equal(releaseEligible({job:'release_decision',approval:'false'}),true);
});
test('failed decisions and cleanup cannot publish even when an approval output exists',()=>{
 for(const decisionResult of ['failure','skipped','cancelled','pending']){
  assert.equal(releaseEligible({decisionResult,approval:'true'}),false);
 }
});
test('decision issues are closed even after errors or cancellation',()=>{
 const cleanup=workflow.release_decision.steps.find(step=>step.name==='Close the decision issue');
 assert.match(cleanup.if,/always\(\)/);
 assert.match(cleanup.if,/issue_number != ''/);
 assert.match(cleanup.run,/--close "\$ISSUE_NUMBER"/);
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
 for(const job of ['release_decision','publish']){
  for(const required of ['failure','skipped','cancelled','pending'])assert.equal(releaseEligible({required,job}),false);
 }
 assert.equal(releaseEligible({cancelled:true}),false);
});
test('PRs, merge groups and manual or bot dispatches never request release approval',()=>{
 for(const event of ['pull_request','merge_group','workflow_dispatch']){
  for(const job of ['release_decision','publish']){
   for(const ref of ['refs/heads/main','refs/heads/feature/releases'])assert.equal(releaseEligible({event,ref,job}),false);
  }
 }
});
test('forks, tags and unrelated branches never request release approval',()=>{
 for(const job of ['release_decision','publish']){
  assert.equal(releaseEligible({repository:'someone/fork',job}),false);
  for(const ref of ['refs/tags/v1.0.0','refs/heads/other'])assert.equal(releaseEligible({ref,job}),false);
 }
});
