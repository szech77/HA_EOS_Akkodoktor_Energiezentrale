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
