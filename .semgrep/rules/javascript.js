// Scanner fixtures only; never execute this file.
// ruleid: eos.javascript.dynamic-code
eval(code);
// ruleid: eos.javascript.dynamic-code
new Function('value', code);
// ok: eos.javascript.dynamic-code
JSON.parse(code);
// ruleid: eos.javascript.wildcard-message-target
window.parent.postMessage(message, '*');
// ruleid: eos.javascript.wildcard-message-target
window.parent.postMessage(message, {targetOrigin:'*'});
// ok: eos.javascript.wildcard-message-target
window.parent.postMessage(message, location.origin);
// ruleid: eos.javascript.untrusted-dom-html
document.body.innerHTML = location.hash;
window.addEventListener('message', (event) => {
  // ruleid: eos.javascript.untrusted-dom-html
  node.insertAdjacentHTML('beforeend', event.data);
  // ok: eos.javascript.untrusted-dom-html
  node.innerHTML = html(event.data);
  // ok: eos.javascript.untrusted-dom-html
  node.innerHTML = DOMPurify.sanitize(event.data);
  // ok: eos.javascript.untrusted-dom-html
  node.textContent = event.data;
});
window.addEventListener('message', async (event) => {
  // ruleid: eos.javascript.untrusted-dom-html
  node.outerHTML = event.data;
});
