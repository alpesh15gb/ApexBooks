// Only live, in-memory operations are tracked. No request bodies or credentials
// are copied here; the originating form remains the owner of its retry closure.
const requests = new Set();
export function registerPostingRequest(request) {
  requests.add(request);
  return () => requests.delete(request);
}
export function hasPendingPostings() {
  return [...requests].some(request => request.busy || request.pending);
}
export const postingNavigationMessage = 'Finish or retry the pending save before leaving this workspace. Its result is not yet confirmed; keeping this form open preserves the original request and prevents a duplicate.';

export const memoryPostingRecoveryMessage = 'Recovery is kept only in this tab. Do not reload, close the tab or sign out until the result is confirmed. After interruption, verify the original result before trying again.';
