// Overwatch's sidebar panel: its web app in an iframe, with the address kept
// in step so /overwatch/cameras/driveway in Home Assistant opens that page.
// Home Assistant hands the panel what follows /overwatch in `route.path`;
// Overwatch (framed) reports each page it moves to, and the address bar follows.
class OverwatchPanel extends HTMLElement {
  set panel(panel) {
    this._base = String(panel.config.url || '').replace(/\/+$/, '')
    this._show()
  }

  set route(route) {
    this._prefix = route.prefix
    this._path = route.path
    this._show()
  }

  // On a phone Home Assistant's sidebar is hidden behind a menu button, which
  // its own panels carry in their top bar: keep a slim one for it.
  set narrow(narrow) {
    this._narrow = narrow
    this._show()
  }

  set hass(hass) {
    this._hass = hass
    if (this._menu) this._menu.hass = hass
  }

  connectedCallback() {
    this._onMessage = event => {
      const frame = this._frame
      if (!frame || event.source !== frame.contentWindow || event.origin !== new URL(this._base).origin) return
      const msg = event.data
      if (!msg || msg.type !== 'overwatch:route' || typeof msg.path !== 'string' || !msg.path.startsWith('/')) return
      // The frame is already there: remember it so the next route change doesn't reload it.
      this._src = this._base + msg.path
      history.replaceState(history.state, '', (this._prefix || '/overwatch') + (msg.path === '/' ? '' : msg.path))
    }
    window.addEventListener('message', this._onMessage)
  }

  disconnectedCallback() {
    window.removeEventListener('message', this._onMessage)
  }

  _show() {
    if (!this._base || this._prefix === undefined) return
    if (!this._frame) {
      // The panel gets no height of its own: take the window's.
      this.style.cssText = 'display:flex;flex-direction:column;height:100vh;height:100dvh;background:var(--primary-background-color)'
      this._bar = document.createElement('div')
      this._bar.style.cssText =
        'flex:none;display:none;align-items:center;height:48px;padding:0 4px;background:var(--app-header-background-color);color:var(--app-header-text-color,#fff)'
      this._menu = document.createElement('ha-menu-button')
      this._menu.hass = this._hass
      this._bar.appendChild(this._menu)
      this.appendChild(this._bar)
      const frame = document.createElement('iframe')
      // Talk needs the microphone, which a frame gets only if the page allows it.
      frame.allow = 'microphone; fullscreen; clipboard-write'
      frame.style.cssText = 'display:block;flex:1;width:100%;min-height:0;border:0'
      this.appendChild(frame)
      this._frame = frame
    }
    this._menu.narrow = !!this._narrow
    this._bar.style.display = this._narrow ? 'flex' : 'none'
    const src = this._base + (this._path || '/') + location.search + location.hash
    if (src !== this._src) {
      this._src = src
      this._frame.src = src
    }
  }
}

customElements.define('overwatch-panel', OverwatchPanel)
