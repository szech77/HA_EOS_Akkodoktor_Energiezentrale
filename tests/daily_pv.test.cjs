/* Backend daily PV energy (presentation.daily_pv_forecast); chart sampling is tested in frontend/. */
const test = require('node:test');
const assert = require('node:assert/strict');
const backend=require('./backend.cjs');
const dailySolar=(rows,now,zone)=>backend('dailySolar',rows,{now,zone});
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
