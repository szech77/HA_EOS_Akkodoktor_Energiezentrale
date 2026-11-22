import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// The bundle is served by the integration next to the existing panel files and loaded by
// bootstrap.js as a classic script, so it is built as one self-contained IIFE.
const outDir = fileURLToPath(new URL('../custom_components/eos_energiezentrale/energy/web/vue', import.meta.url))

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  define: {
    // Library builds do not replace these automatically; production values for the runtime-only Vue build.
    'process.env.NODE_ENV': JSON.stringify('production'),
    __VUE_OPTIONS_API__: 'false',
    __VUE_PROD_DEVTOOLS__: 'false',
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false',
  },
  build: {
    outDir,
    emptyOutDir: true,
    target: 'es2022',
    sourcemap: false,
    cssCodeSplit: false,
    lib: {
      entry: fileURLToPath(new URL('./src/main.ts', import.meta.url)),
      formats: ['iife'],
      name: 'EosVue',
      fileName: () => 'eos-vue.js',
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.spec.ts'],
    restoreMocks: true,
    // Some tests build their data with the Python backend (src/test/backend.ts); starting it takes seconds.
    testTimeout: 30_000,
  },
})
