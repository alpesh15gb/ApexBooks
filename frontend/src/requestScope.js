// A response may update a workspace only while its original context is active.
// The generation also rejects an old response after switching away and back.
export function createRequestScope(initialContext) {
  let context = initialContext;
  let generation = 0;
  let latest = 0;
  return {
    setContext(next) {
      if (next !== context) {
        context = next;
        generation++;
        latest++;
      }
    },
    capture() {
      const captured = generation;
      return () => captured === generation;
    },
    latest() {
      const captured = generation;
      const request = ++latest;
      return () => captured === generation && request === latest;
    },
  };
}
