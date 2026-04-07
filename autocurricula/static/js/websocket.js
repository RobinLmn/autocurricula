import { state } from './state.js';

let _handlers = {};

export function setHandlers(h) {
  _handlers = h;
}

export function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  state.ws = new WebSocket(`${proto}//${location.host}/ws`);
  state.ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    const fn = _handlers[msg.type];
    if (fn) fn(msg);
  };
  state.ws.onclose = () => setTimeout(connect, 2000);
}

export function send(msg) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify(msg));
  }
}
