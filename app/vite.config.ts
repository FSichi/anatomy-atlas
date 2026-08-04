import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
    plugins: [react(), tailwindcss()],
    // El puerto lo asigna el entorno: sin fijarlo, dos sesiones pueden convivir.
    server: { port: Number(process.env.PORT) || 5180 },
    build: {
        // Los GLB ya vienen comprimidos con Draco: que Vite no los reprocese.
        assetsInlineLimit: 0,
    },
});
