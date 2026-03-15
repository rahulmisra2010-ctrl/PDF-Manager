// Jest setup file for React testing
// This file is automatically run before each test suite

// Suppress known third-party library warnings
const originalWarn = console.warn;
console.warn = (...args) => {
  if (
    args[0] &&
    typeof args[0] === 'string' &&
    (args[0].includes('ReactDOM.render') || args[0].includes('act('))
  ) {
    return;
  }
  originalWarn(...args);
};
