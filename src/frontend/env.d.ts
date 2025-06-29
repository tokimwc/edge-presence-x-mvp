/// <reference types="vite/client" />

declare module 'three' {
  interface Scene {
    backgroundNeedsUpdate?: boolean;
  }
} 