/* Deterministic AC-bus example, never used for device control. Powers are W,
 * interval energy is Wh; charging losses affect stored energy, not bus balance. */
'use strict';
const HOUR=3600000, STEP=120000, NOW=Date.parse('2026-11-09T11:00:00Z');
const iso=stamp=>new Date(stamp).toISOString();
const BATTERY={capacity:11059,efficiency:.95,min:.2,max:1,maxPower:4760};
const CAR={capacity:77000,efficiency:.9,target:.7,pvTarget:.8,maxPower:11000};
const PV_PRICE=.08;
const emptyAmount=()=>({kwh:0,cost_eur:0,cost_unknown_kwh:0,seconds:0,
 sources:Object.fromEntries(['pv','battery','grid','unknown'].map(key=>[key,{kwh:0,cost_eur:0,cost_unknown_kwh:0}]))});

function createDemo(){
 const rows=[], consumers=Object.fromEntries(['house','heat','car'].map(key=>[key,{total:emptyAmount()}]));
 let batteryWh=BATTERY.capacity*.45,carWh=CAR.capacity*.28,batteryCost=batteryWh/1000*.14;
 const dt=STEP/HOUR;
 for(let stamp=NOW-24*HOUR;stamp<=NOW+72*HOUR;stamp+=STEP){
  const date=new Date(stamp),h=date.getUTCHours()+1+date.getUTCMinutes()/60;
  const calendar=iso(stamp+HOUR).slice(0,10),future=stamp>NOW;
  const daylight=Math.max(0,Math.sin((h-7.5)/9*Math.PI));
  const solar=h>=7.5&&h<=16.5?6200*daylight*(calendar==='2026-11-10'?.85:calendar==='2026-11-11'?.72:1):0;
  const house=h>=7&&h<8?1700:h>=18&&h<19?1800:850,heat=500;
  const price=h>=2&&h<5?24:h>=17&&h<21?44:h>=10&&h<16?28.4:34;
  const surplus=Math.max(0,solar-house-heat);
  const cheapBattery=future&&calendar==='2026-11-10'&&h>=2&&h<4&&batteryWh<BATTERY.capacity*.8;
  let charge=Math.min(surplus,1400,(BATTERY.capacity-batteryWh)/(dt*BATTERY.efficiency));
  if(cheapBattery)charge=Math.min(1800,(BATTERY.capacity*.8-batteryWh)/(dt*BATTERY.efficiency));
  charge=Math.max(0,charge);
  const evGrid=future&&calendar==='2026-11-10'&&h>=2&&h<7.5&&carWh<CAR.capacity*CAR.target;
  const remainingPV=Math.max(0,surplus-charge);
  const phases=remainingPV>=4140?3:1;
  const amps=Math.min(16,Math.floor(remainingPV/(phases*230)*10+1e-9)/10);
  let car=evGrid?CAR.maxPower:amps>=6?phases*230*amps:0;
  const target=evGrid?CAR.target:CAR.pvTarget;
  car=Math.max(0,Math.min(car,(CAR.capacity*target-carWh)/(dt*CAR.efficiency)));
  const discharge=charge>0||car>0?0:Math.max(0,Math.min(house+heat-solar,
    BATTERY.maxPower,(batteryWh-BATTERY.capacity*BATTERY.min)*BATTERY.efficiency/dt));
  const battery=charge-discharge,grid=house+heat+car+battery-solar;
  const batteryMode=cheapBattery?'FORCED_CHARGE':solar>house+heat?'NON_EXPORT':'SELF_CONSUMPTION';
  const carMode=car>0?(evGrid?'GRID_SUPPORT_IMPORT':'NON_EXPORT'):'IDLE';
  const row={time:iso(stamp),end:iso(stamp+STEP),solar,house,heat,car,house_total:house+heat+car,
    battery,battery_charge:charge,battery_discharge:discharge,grid,price,
    battery_soc:batteryWh/BATTERY.capacity*100,car_soc:carWh/CAR.capacity*100,
    battery_mode:batteryMode,car_mode:carMode,car_actual_mode:car>0?'CHARGING':'IDLE',
    phases:evGrid?3:phases,amps:car/(230*(evGrid?3:phases))};
  rows.push(row);
  // Attribute simultaneous sources proportionally among consumers. PV used to
  // charge the house battery is removed before attributing direct consumer PV.
  const demand=house+heat+car,pvForBattery=Math.min(solar,charge);
  const pvForLoads=Math.min(demand,Math.max(0,solar-pvForBattery));
  const batteryForLoads=discharge,gridForLoads=Math.max(0,demand-pvForLoads-batteryForLoads);
  const drawnWh=discharge*dt/BATTERY.efficiency;
  const withdrawnCost=batteryWh>0?batteryCost*drawnWh/batteryWh:0;
  if(calendar==='2026-11-09'&&stamp<NOW){
   for(const key of ['house','heat','car']){
    const total=consumers[key].total,share=row[key]/demand;
    total.seconds+=STEP/1000;
    for(const [source,power,cost] of [['pv',pvForLoads,pvForLoads*dt/1000*PV_PRICE],
      ['battery',batteryForLoads,withdrawnCost],['grid',gridForLoads,gridForLoads*dt/1000*price/100]]){
     const kwh=power*share*dt/1000,eur=cost*share;
     total.sources[source].kwh+=kwh;total.sources[source].cost_eur+=eur;
     total.kwh+=kwh;total.cost_eur+=eur;
    }
   }
  }
  batteryCost-=withdrawnCost;
  batteryCost+=(pvForBattery*PV_PRICE+(charge-pvForBattery)*price/100)*dt/1000;
  batteryWh+=charge*dt*BATTERY.efficiency-drawnWh;
  carWh+=car*dt*CAR.efficiency;
 }
 const live={...rows.find(row=>Date.parse(row.time)===NOW),weather:{condition:'partlycloudy',temperature:12.5,unit:'°C'},
   car_status:'charging',car_control:'charging',battery_control:'limits',soc_source:'estimate',departure:'2026-11-10T06:30:00Z'};
 const modePlan=key=>{
  const plan=[];
  for(const row of rows.filter(row=>Date.parse(row.time)>=NOW&&Date.parse(row.time)<=NOW+24*HOUR)){
   const mode=row[key+'_mode'];
   if(plan.at(-1)?.mode!==mode)plan.push({time:row.time,mode});
  }
  return plan;
 };
 const snapshot={vehicle_name:'E-Auto',live,
  settings:{schedule:'weekly',departure:'',departure_time:'07:30',weekdays:[0,1,2,3,4],target_soc:70,pv_target_soc:80,
   reserve_w:0,pv:true,fast:false,battery_pv_support:true,phase_auto:true,regulation_interval_s:20,battery_min_soc:20,battery_max_soc:100},
  armed:true,errors:{},features:{car:true,heat:true},plan:{battery:modePlan('battery'),car:modePlan('car')},
  forecast:rows.filter(row=>Date.parse(row.time)>=NOW),zone:'Europe/Berlin',plan_end:iso(NOW+24*HOUR),
  power_reference:{solar:10000,car:11000,battery_charge:4760,battery_discharge:4760},
  battery_limits:{managed:true,confirmed:true},accounting:{date:'2026-11-09',consumers}};
 return {snapshot,rows,now:NOW,step:STEP,battery:BATTERY,car:CAR};
}
module.exports={createDemo};
