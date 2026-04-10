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

export function showLoading(label, cancellable = false) {
  $('#loading-label').textContent = label || 'Loading...';
  $('#loading-tokens').classList.add('hidden');
  $('#loading-tokens').textContent = '';
  $('#loading-cancel').classList.toggle('hidden', !cancellable);
  $('#loading-overlay').classList.remove('hidden');
}

export function hideLoading() {
  $('#loading-overlay').classList.add('hidden');
  $('#loading-cancel').classList.add('hidden');
  $('#loading-tokens').classList.add('hidden');
  $('#loading-tokens').textContent = '';
}

function formatTokens(n) {
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
  return String(n);
}

export function updateLoadingProgress(step, data) {
  $('#loading-label').textContent = step;
  if (data.total_tokens > 0) {
    const parts = [`${formatTokens(data.total_tokens)} tokens`];
    if (data.cost_usd > 0) parts.push(`$${data.cost_usd.toFixed(3)}`);
    $('#loading-tokens').textContent = parts.join(' · ');
    $('#loading-tokens').classList.remove('hidden');
  }
}
