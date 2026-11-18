/* Render tests consume the actual Python backend contract, not duplicated JS policy. */
const fs=require('node:fs'),path=require('node:path'),{execFileSync}=require('node:child_process');
const root=path.join(__dirname,'..');
const python=[process.env.PYTHON,path.join(root,'.venv/Scripts/python.exe'),path.join(root,'.venv/bin/python')]
  .find(value=>value&&fs.existsSync(value))??'python';
const script=`import json,sys
from datetime import datetime,timezone
from custom_components.eos_energiezentrale.energy.report_values import amount_values,current_day_values
from custom_components.eos_energiezentrale.energy.status import view_state
from custom_components.eos_energiezentrale.energy.presentation import daily_pv_forecast,next24_pv_forecast,plan_events,node_problems
from custom_components.eos_energiezentrale.energy.charge_view import charge_plan
args=json.load(sys.stdin)
now=datetime.fromtimestamp(args.get('now',0)/1000,timezone.utc)
op=args['operation']
if op=='amount': result=amount_values(args['data'])
elif op=='report': result=current_day_values(args['data'],args.get('historical'),args.get('consumers',['house','heat','car']))
elif op=='view': result=view_state(args['data'],now)
elif op=='dailySolar': result=daily_pv_forecast(args['data'],now,args['zone'])
elif op=='pvSummary': result=next24_pv_forecast(args['data'],now)
elif op=='planEvents': result=plan_events(args['data'],now)
elif op=='chargePlan': result=charge_plan(args['data'],now,args.get('pv_price_ct'))
elif op=='nodeProblems': result=node_problems(args['data'],args.get('vehicles',[]))
else: raise ValueError('Unknown test operation')
print(json.dumps(result,allow_nan=False))`;
const cache=new Map();
module.exports=(operation,data,options={})=>{
  const input=JSON.stringify({operation,data,...options});
  if(!cache.has(input))cache.set(input,execFileSync(python,['-X','utf8','-c',script],{cwd:root,input,encoding:'utf8'}));
  return JSON.parse(cache.get(input));
};
