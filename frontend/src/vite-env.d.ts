/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DEMO_ADMIN_EMAIL?: string;
  readonly VITE_DEMO_ADMIN_PASSWORD?: string;
  readonly VITE_DEMO_USER_EMAIL?: string;
  readonly VITE_DEMO_USER_PASSWORD?: string;
  readonly VITE_DEMO_USER_TWO_EMAIL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
