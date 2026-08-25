import '@testing-library/jest-dom/vitest';

// The real page carries the session token; the tests stand in for that.
window.__JOBSHEET__ = { token: 'test-token', version: '0.1.0.dev0' };

// jsdom has neither, and both are used by the interface.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

if (!('EventSource' in window)) {
  class FakeEventSource {
    onerror: (() => void) | null = null;
    addEventListener() {}
    close() {}
  }
  (window as unknown as { EventSource: unknown }).EventSource = FakeEventSource;
}
