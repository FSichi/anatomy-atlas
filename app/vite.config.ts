import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
    // GitHub Pages sirve el sitio bajo /anatomy-atlas/, no en la raíz del
    // dominio. En desarrollo queda en '/'. Todo asset se resuelve contra esto
    // mediante lib/asset-url.ts.
    base: process.env.GITHUB_PAGES ? '/anatomy-atlas/' : '/',
    plugins: [react(), tailwindcss()],
    // El puerto lo asigna el entorno: sin fijarlo, dos sesiones pueden convivir.
    server: { port: Number(process.env.PORT) || 5180 },
    build: {
        // Los GLB ya vienen comprimidos con Draco: que Vite no los reprocese.
        assetsInlineLimit: 0,
    },
});
