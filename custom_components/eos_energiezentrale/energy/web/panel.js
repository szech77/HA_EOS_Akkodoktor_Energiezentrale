/* HA owns authentication. No access tokens enter the iframe or its URL. */
class EnergyPanel extends HTMLElement {
  set hass(value) { this._hass = value; }
  connectedCallback() {
    if (this.frame) return;
    // HA's custom-panel wrapper has no definite height for percentage sizing.
    this.style.cssText = 'display:block;width:100%;height:100vh;height:100dvh;min-width:0;min-height:0;overflow:hidden;box-sizing:border-box;';
    this.frame = document.createElement('iframe');
    this.frame.title = 'EOS Energiezentrale';
    this.frame.style.cssText = 'width:100%;height:100%;border:0;display:block;';
    this.frame.src = '/eos-energiezentrale-static/index.html';
    this.append(this.frame);
    this.listener = async event => {
      if (event.source !== this.frame.contentWindow || event.origin !== location.origin
          || event.data?.channel !== 'eos-energy-request') return;
      const {id, action, values} = event.data;
      if (!Number.isSafeInteger(id)) return;
      try {
        const result = await this._hass.callWS({type:'eos_energiezentrale/request', action,
          values:values ?? {}, language:this._hass.locale?.language ?? this._hass.language});
        event.source.postMessage({channel:'eos-energy-response', id, result}, location.origin);
      } catch (error) {
        event.source.postMessage({channel:'eos-energy-response', id,
          error:error.code ?? 'request_failed'}, location.origin);
      }
    };
    window.addEventListener('message', this.listener);
  }
  disconnectedCallback() {
    window.removeEventListener('message', this.listener);
    this.frame?.remove();
    this.frame = null;
  }
}
if (!customElements.get('eos-energy-panel')) customElements.define('eos-energy-panel', EnergyPanel);
