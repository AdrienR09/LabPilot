/// <reference types="vite/client" />

// `import.meta.env` is Vite's, and without this reference TypeScript sees
// a bare `ImportMeta` and rejects `api/index.ts`'s first two lines — the
// other half of why that module did not compile.

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_WS_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
