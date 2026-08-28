import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],
    server: {
        // Dev-only: the built app is served same-origin by FastAPI in production/Docker,
        // so no proxy/CORS setup is needed there.
        proxy: {
            "/api": "http://localhost:8000",
        },
    },
});
