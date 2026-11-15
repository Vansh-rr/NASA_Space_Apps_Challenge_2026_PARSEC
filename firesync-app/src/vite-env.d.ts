/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SATELLITE_TILES?: string;
  readonly VITE_SATELLITE_ATTRIBUTION?: string;
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
