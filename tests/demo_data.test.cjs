const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createDemo}=require('../tools/demo-data.cjs');
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-7,`${a} != ${b}`);

test('demo conserves AC power at every historical and future sample, including the live view',()=>{
 const {rows,snapshot}=createDemo();
 for(const row of [...rows,snapshot.live]){
  near(row.solar+Math.max(0,row.grid)+row.battery_discharge,
    row.house+row.heat+row.car+row.battery_charge+Math.max(0,-row.grid));
  near(row.house_total,row.house+row.heat+row.car);
  assert.ok(!(row.battery_charge>0&&row.battery_discharge>0));
 }
 const latest=rows.find(row=>row.time===snapshot.live.time);
 for(const key of ['solar','house','heat','car','battery','grid','battery_soc','car_soc'])near(latest[key],snapshot.live[key]);
});

test('demo SoC changes follow actual charging power, capacity and losses',()=>{
 const {rows,step,battery,car}=createDemo(),dt=step/3600000;
 for(let i=0;i<rows.length-1;i++){
  const a=rows[i],b=rows[i+1];
  near((b.battery_soc-a.battery_soc)*battery.capacity/100,
    (a.battery_charge*battery.efficiency-a.battery_discharge/battery.efficiency)*dt);
  near((b.car_soc-a.car_soc)*car.capacity/100,a.car*car.efficiency*dt);
  assert.ok(a.battery_soc>=20-1e-8&&a.battery_soc<=100+1e-8);
  assert.ok(a.car_soc>=0&&a.car_soc<=80+1e-8);
  assert.ok(a.car<=11000+1e-8&&a.battery_charge<=4760+1e-8&&a.battery_discharge<=4760+1e-8);
 }
});

test('daily demo energies integrate measured intervals; sources and costs add up',()=>{
 const {rows,snapshot,now,step}=createDemo();
 const today=rows.filter(row=>Date.parse(row.time)<now&&row.time>='2026-11-08T23:00:00.000Z');
 for(const key of ['house','heat','car']){
  const total=snapshot.accounting.consumers[key].total;
  near(total.kwh,today.reduce((sum,row)=>sum+row[key]*step/3600000000,0));
  near(total.kwh,Object.values(total.sources).reduce((sum,item)=>sum+item.kwh,0));
  near(total.cost_eur,Object.values(total.sources).reduce((sum,item)=>sum+item.cost_eur,0));
  assert.ok(total.cost_eur>=0);
  near(total.sources.pv.cost_eur,total.sources.pv.kwh*.082);
 }
});

test('planned vehicle modes match charging behavior and the departure target is reached',()=>{
 const {rows,snapshot}=createDemo();
 const deadline=Date.parse(snapshot.live.departure),now=Date.parse(snapshot.live.time);
 for(const row of rows.filter(row=>Date.parse(row.time)>=now&&Date.parse(row.time)<now+86400000)){
  const mode=snapshot.plan.car.filter(item=>Date.parse(item.time)<=Date.parse(row.time)).at(-1).mode;
  assert.equal(mode,row.car_mode);
  assert.equal(mode==='IDLE',row.car===0);
 }
 assert.ok(rows.find(row=>Date.parse(row.time)===deadline).car_soc>=70-1e-7);
});


test('documentation uses 8.2 ct/kWh PV opportunity cost and a priced initial grid charge',()=>{
 const {tariffs}=createDemo();
 near(tariffs.pv,.082);
 near(tariffs.initialGrid,.24);
});
