export const state = {
  ws: null,
  editor: null,
  currentProblem: null,
  syncTimeout: null,
  pendingEditorCode: null,
  autocompleteEnabled: true,
  pendingNext: null,
  derivEditor: null,
  chatBusy: false,
};

export const pendingRequests = {};

export const $ = (s) => document.querySelector(s);
export const $$ = (s) => document.querySelectorAll(s);

export function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

let _timerInterval = null;
let _timerStart = 0;
let _lastStep = '';
let _hasTokens = false;

function _startTimer() {
  _stopTimer();
  _timerStart = Date.now();
  _hasTokens = false;
  _updateTimerDisplay();
  _timerInterval = setInterval(_updateTimerDisplay, 1000);
}

function _stopTimer() {
  if (_timerInterval) {
    clearInterval(_timerInterval);
    _timerInterval = null;
  }
}

function _updateTimerDisplay() {
  if (_hasTokens) return;
  const el = $('#loading-tokens');
  const elapsed = Math.floor((Date.now() - _timerStart) / 1000);
  if (elapsed >= 1) {
    el.textContent = `${elapsed}s`;
    el.classList.remove('hidden');
  }
}

function formatTokens(n) {
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
  return String(n);
}

export function showLoading(label, cancellable = false) {
  $('#loading-label').textContent = label || 'Loading...';
  $('#loading-tokens').classList.add('hidden');
  $('#loading-tokens').textContent = '';
  $('#loading-cancel').classList.toggle('hidden', !cancellable);
  $('#loading-overlay').classList.remove('hidden');
  _lastStep = '';
  if (cancellable) {
    _startTimer();
  } else {
    _stopTimer();
  }
}

export function hideLoading() {
  _stopTimer();
  $('#loading-overlay').classList.add('hidden');
  $('#loading-cancel').classList.add('hidden');
  $('#loading-tokens').classList.add('hidden');
  $('#loading-tokens').textContent = '';
}

export function updateLoadingProgress(step, data) {
  $('#loading-label').textContent = step;
  if (data.total_tokens > 0) {
    _hasTokens = true;
    const elapsed = Math.floor((Date.now() - _timerStart) / 1000);
    const parts = [`${formatTokens(data.total_tokens)} tokens`];
    if (elapsed >= 1) parts.push(`${elapsed}s`);
    $('#loading-tokens').textContent = parts.join(' \u00b7 ');
    $('#loading-tokens').classList.remove('hidden');
  }
  _lastStep = step;
}
