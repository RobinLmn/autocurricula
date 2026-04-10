import { $, state } from './state.js';

let _handlers = {};
let _retries = 0;
const MAX_RETRIES = 3;

export function setHandlers(h) {
  _handlers = h;
}

export function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  state.ws = new WebSocket(`${proto}//${location.host}/ws`);
  state.ws.onopen = () => { _retries = 0; hideDisconnected(); };
  state.ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    const fn = _handlers[msg.type];
    if (fn) fn(msg);
  };
  state.ws.onclose = () => {
    _retries++;
    if (_retries <= MAX_RETRIES) {
      setTimeout(connect, 2000);
    } else {
      showDisconnected();
    }
  };
}

function showDisconnected() {
  let el = $('#disconnected-overlay');
  if (!el) {
    el = document.createElement('div');
    el.id = 'disconnected-overlay';
    el.innerHTML = `<div id="disconnected-content">
      <p id="disconnected-label">Disconnected</p>
      <p id="disconnected-hint">Run <code>autocurricula</code> in your terminal to restart</p>
    </div>`;
    document.body.appendChild(el);
  }
}

function hideDisconnected() {
  const el = $('#disconnected-overlay');
  if (el) el.remove();
}

export function send(msg) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify(msg));
  }
}
