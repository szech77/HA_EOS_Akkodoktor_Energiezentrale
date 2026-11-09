const test = require('node:test');
const assert = require('node:assert/strict');
const {points,at} = require('../custom_components/eos_energiezentrale/energy/web/chart-data.js');
const now=Date.parse('2026-11-09T12:00:00Z');
const iso=n=>new Date(now+n).toISOString();
test('Missing and malformed readings are gaps, while signed flows and zero remain valid',()=>{
  const rows=[{time:iso(0),power:-470},{time:iso(-1000),power:0},{time:iso(-2000),power:null},{time:'bad',power:200},{time:iso(1000),power:Infinity}];
  assert.deepEqual(points(rows,'power',now-5000,now+5000).map(p=>p.value),[0,-470]);
});
test('Historical values use nearby samples without extrapolating across long outages',()=>{
  const series={actual:[{stamp:now-60000,value:-470}],future:[]};
  assert.equal(at(series,now,now).point.value,-470);
  assert.equal(at(series,now-60000-360001,now),null);
  assert.equal(at(series,now+1,now),null);
});
test('Forecast values follow interval boundaries, including slots already in progress',()=>{
  const series={actual:[],future:[{stamp:now-60000,end:now+60000,value:4000},{stamp:now+60000,end:now+120000,value:2000}]};
  assert.equal(at(series,now+1,now).point.value,4000);
  assert.equal(at(series,now+60000,now).point.value,2000);
  assert.equal(at(series,now+120000,now),null);
  assert.equal(at(series,now,now),null);
});

const {dailySolar}=require('../custom_components/eos_energiezentrale/energy/web/chart-data.js');
test('Daily PV energy clips midnight slots, avoids overlap and marks missing days',()=>{
  const now=Date.parse('2026-11-09T22:00:00Z'); // 23:00 Berlin
  const rows=[{time:'2026-11-09T22:00:00Z',end:'2026-11-10T00:00:00Z',solar:2000},
              {time:'2026-11-09T22:00:00Z',end:'2026-11-10T00:00:00Z',solar:2000}];
  const result=dailySolar(rows,now,'Europe/Berlin');
  assert.equal(result[0].kwh,2);
  assert.equal(result[0].complete,true);
  assert.equal(result[1].kwh,2);
  assert.equal(result[1].complete,false);
  assert.equal(result[2].kwh,null);
});
test('Calendar energy respects the 23-hour daylight-saving day',()=>{
  const start='2026-03-28T23:00:00Z', end='2026-03-29T22:00:00Z';
  const result=dailySolar([{time:start,end,solar:1000}],Date.parse(start),'Europe/Berlin');
  assert.equal(result[0].kwh,23);
  assert.equal(result[0].complete,true);
});
test('A measured zero forecast is different from absent or invalid forecast values',()=>{
  const start='2026-11-09T00:00:00Z';
  const result=dailySolar([{time:start,end:'2026-11-10T00:00:00Z',solar:0}],Date.parse(start),'UTC');
  assert.equal(result[0].kwh,0);
  assert.equal(result[0].complete,true);
  assert.equal(result[1].kwh,null);
});


test('power rings use a linear clockwise fraction and signed battery magnitude',()=>{
  const {powerFraction}=require('../custom_components/eos_energiezentrale/energy/web/chart-data.js');
  assert.equal(powerFraction(2500,10000),.25);
  assert.equal(powerFraction(-1190,4760),.25);
  assert.equal(powerFraction(0,10000),0);
  assert.equal(powerFraction(12000,10000),1);
  for(const [value,max] of [[null,1000],[NaN,1000],[100,null],[100,0]])assert.equal(powerFraction(value,max),null);
});
