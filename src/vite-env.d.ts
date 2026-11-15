/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SATELLITE_TILES?: string;
  readonly VITE_SATELLITE_ATTRIBUTION?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
