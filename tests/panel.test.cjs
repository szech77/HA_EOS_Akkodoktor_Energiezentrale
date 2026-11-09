'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function panelFixture() {
  let Panel, listener;
  const frame = {style:{}, contentWindow:{postMessage(){}}, remove(){}};
  const origin = 'https://homeassistant.example';
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,
    '../custom_components/eos_energiezentrale/energy/web/panel.js'), 'utf8'), {
    HTMLElement: class {style = {}; append(){}},
    customElements: {get(){}, define(_name, value){Panel = value;}},
    location:{origin}, document:{createElement(){return frame;}},
    window:{addEventListener(_name, value){listener = value;}, removeEventListener(){}}
  });
  const panel = new Panel();
  const calls = [];
  panel.hass = {locale:{language:'de'}, callWS:async message => {calls.push(message); return {ok:true};}};
  panel.connectedCallback();
  return {panel, frame, calls, origin, send:message => listener(message)};
}

test('only the actual same-origin iframe can issue authenticated requests', async () => {
  const f = panelFixture();
  const data = {channel:'eos-energy-request', id:1, action:'control', values:{enabled:true}};
  await f.send({source:{}, origin:f.origin, data});
  await f.send({source:f.frame.contentWindow, origin:'https://foreign.example', data});
  assert.equal(f.calls.length, 0);
  await f.send({source:f.frame.contentWindow, origin:f.origin, data});
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0].language, 'de');
  assert.equal(f.calls[0].type, 'eos_energiezentrale/request');
});

test('HA errors are returned without credentials or raw exception messages', async () => {
  const f = panelFixture();
  f.panel.hass = {locale:{language:'en'}, callWS:async () => {throw {code:'unauthorized', message:'private detail'};}};
  let reply;
  f.frame.contentWindow.postMessage = (data, origin) => {reply = {data,origin};};
  await f.send({source:f.frame.contentWindow, origin:f.origin,
    data:{channel:'eos-energy-request',id:2,action:'snapshot'}});
  assert.equal(reply.data.error, 'unauthorized');
  assert.equal(reply.origin, f.origin);
  assert.ok(!JSON.stringify(reply).includes('private detail'));
});


test('the HA build version propagates to the iframe and changes after an update',()=>{
  const f=panelFixture();
  f.panel.panel={config:{asset_version:'build-one'}};
  assert.ok(f.frame.src.includes('index.html?v=build-one'));
  assert.ok(f.frame.src.includes('lang=de'));
  f.panel.panel={config:{asset_version:'build-two'}};
  assert.ok(f.frame.src.includes('index.html?v=build-two'));
});

test('an early request reports bridge readiness without attempting a missing HA connection',async()=>{
  const f=panelFixture();f.panel.hass=undefined;let reply;
  f.frame.contentWindow.postMessage=data=>{reply=data;};
  await f.send({source:f.frame.contentWindow,origin:f.origin,data:{channel:'eos-energy-request',id:4,action:'language'}});
  assert.equal(reply.error,'bridge_not_ready');
  assert.equal(f.calls.length,0);
});


test('a response from an earlier iframe build is discarded after navigation',async()=>{
  const f=panelFixture();let release,reply;
  f.panel.hass={locale:{language:'de'},callWS:()=>new Promise(resolve=>{release=resolve;})};
  f.frame.contentWindow.postMessage=data=>{reply=data;};
  const request=f.send({source:f.frame.contentWindow,origin:f.origin,data:{channel:'eos-energy-request',id:5,action:'language',client:'old-frame'}});
  f.panel.panel={config:{asset_version:'updated-build'}};
  release({ok:true});await request;
  assert.equal(reply,undefined);
});

test('the iframe identity is echoed so retry cannot consume an old response',async()=>{
  const f=panelFixture();let reply;f.frame.contentWindow.postMessage=data=>{reply=data;};
  await f.send({source:f.frame.contentWindow,origin:f.origin,data:{channel:'eos-energy-request',id:6,action:'snapshot',client:'current-frame'}});
  assert.equal(reply.client,'current-frame');
});
