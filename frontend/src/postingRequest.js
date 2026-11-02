// Keep the exact operation (including its idempotency key and serialized body)
// when a response is uncertain. Never turn an interrupted POST into a new POST.
export function createPostingRequest({ definitiveRetryStatuses = [] } = {}) {
  let active = false;
  let pending = null;
  return {
    get busy() { return active; },
    get pending() { return pending !== null; },
    async run(operation) {
      if (active) return false;
      active = true;
      const retrying = pending !== null;
      pending ||= operation;
      try {
        const value = await pending();
        pending = null;
        return { value };
      } catch (error) {
        // Initial 4xx rejections permit correction except 408 (timeout). A retry of an
        // uncertain operation must not unlock editing if its outcome is unknown.
        // A caller may opt into a documented, route-specific no-commit status
        // only when server replay lookup precedes that response (recurring 409).
        if ((!retrying || definitiveRetryStatuses.includes(error.status)) && error.status >= 400 && error.status < 500 && error.status !== 408) pending = null;
        throw error;
      } finally {
        active = false;
      }
    },
  };
}
