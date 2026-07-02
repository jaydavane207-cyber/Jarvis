import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  root: 'src/webview',
  build: {
    outDir: path.resolve(__dirname, 'dist/webview'),
    emptyOutDir: false,
    rollupOptions: {
      input: path.resolve(__dirname, 'src/webview/index.html'),
      output: {
        entryFileNames: 'App.js',
        assetFileNames: '[name].[ext]'
      }
    }
  }
});