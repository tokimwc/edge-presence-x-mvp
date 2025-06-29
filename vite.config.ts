import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import vuetify from 'vite-plugin-vuetify';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vuetify({
      autoImport: true,
    }),
  ],
  publicDir: 'src/frontend/public',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src/frontend'),
      '~': path.resolve(__dirname, './src/lib'),
    },
  },
  /*
  optimizeDeps: {
    include: ['vue-router'],
  },
  */
  server: {
    host: '0.0.0.0',
    port: 5173,
  }
}); 