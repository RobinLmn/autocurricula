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
  $('#loading-cancel').classList.toggle('hidden', !cancellable);
  $('#loading-overlay').classList.remove('hidden');
}

export function hideLoading() {
  $('#loading-overlay').classList.add('hidden');
  $('#loading-cancel').classList.add('hidden');
}
