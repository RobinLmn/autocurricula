export const state = {
  ws: null,
  editor: null,
  currentProblem: null,
  syncTimeout: null,
  pendingEditorCode: null,
  autocompleteEnabled: true,
  pendingNext: null,
  derivEditor: null,
};

export const pendingRequests = {};

export const $ = (s) => document.querySelector(s);
export const $$ = (s) => document.querySelectorAll(s);

export function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

export function showLoading(label) {
  $('#loading-label').textContent = label || 'Loading...';
  $('#loading-overlay').classList.remove('hidden');
}

export function hideLoading() {
  $('#loading-overlay').classList.add('hidden');
}
