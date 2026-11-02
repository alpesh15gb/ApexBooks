// Keep the exact operation (including its idempotency key and serialized body)
// when a response is uncertain. Never turn an interrupted POST into a new POST.
export function createPostingRequest() {
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
        // A 4xx on the initial attempt is a definitive rejection. A retry of an
        // uncertain operation must not unlock editing if its outcome is unknown.
        if (!retrying && error.status >= 400 && error.status < 500) pending = null;
        throw error;
      } finally {
        active = false;
      }
    },
  };
}
