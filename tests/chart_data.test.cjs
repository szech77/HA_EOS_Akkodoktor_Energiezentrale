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
