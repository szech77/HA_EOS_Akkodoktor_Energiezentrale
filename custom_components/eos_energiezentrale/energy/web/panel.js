/* HA owns authentication. No access tokens enter the iframe or its URL. */
class EnergyPanel extends HTMLElement {
  set hass(value) { this._hass = value; if(this.frame)this.updateSource(); }
  set panel(value) {
    this._panel = value;
    if(this.frame)this.updateSource();
  }
  updateSource() {
    const version=this._panel?.config?.asset_version ?? this.fallbackVersion;
    const language=this._hass?.locale?.language??this._hass?.language??'en';
    const key=String(version)+'/'+language;
    if(this.frameVersion===key)return;
    this.frameVersion=key;
    this.frameGeneration=(this.frameGeneration??0)+1;
    this.frame.src='/eos-energiezentrale-static/index.html?v='+encodeURIComponent(version)+'&lang='+encodeURIComponent(language);
  }
  connectedCallback() {
    if (this.frame) return;
    // HA's custom-panel wrapper has no definite height for percentage sizing.
    this.style.cssText = 'display:block;width:100%;height:100vh;height:100dvh;min-width:0;min-height:0;overflow:hidden;box-sizing:border-box;';
    this.frame = document.createElement('iframe');
    this.frame.title = 'EOS Energiezentrale';
    this.frame.style.cssText = 'width:100%;height:100%;border:0;display:block;';
    this.fallbackVersion=String(Date.now());
    this.listener = async event => {
      if (event.source !== this.frame.contentWindow || event.origin !== location.origin
          || event.data?.channel !== 'eos-energy-request') return;
      const {id, action, values} = event.data;
      const client=typeof event.data.client==='string'&&event.data.client.length<=80?event.data.client:undefined;
      if (!Number.isSafeInteger(id)) return;
      const generation=this.frameGeneration;
      try {
        if(!this._hass?.callWS){
          event.source.postMessage({channel:'eos-energy-response',id,client,error:'bridge_not_ready'},location.origin);
          return;
        }
        const result = await this._hass.callWS({type:'eos_energiezentrale/request', action,
          values:values ?? {}, language:this._hass.locale?.language ?? this._hass.language});
        if(generation!==this.frameGeneration)return;
        event.source.postMessage({channel:'eos-energy-response', id, client, result}, location.origin);
      } catch (error) {
        if(generation!==this.frameGeneration)return;
        event.source.postMessage({channel:'eos-energy-response', id, client,
          error:error.code ?? 'request_failed'}, location.origin);
      }
    };
    window.addEventListener('message', this.listener);
    this.updateSource();
    this.append(this.frame);
  }
  disconnectedCallback() {
    window.removeEventListener('message', this.listener);
    this.frame?.remove();
    this.frame = null;
    this.frameVersion = null;
    this.frameGeneration=(this.frameGeneration??0)+1;
  }
}
if (!customElements.get('eos-energy-panel')) customElements.define('eos-energy-panel', EnergyPanel);
