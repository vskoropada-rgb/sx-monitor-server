import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: { "@": path.resolve(__dirname, "./src") },
    },
    server: {
        // dev-проксі на FastAPI, щоб cookie працювали на одному origin
        proxy: {
            "/api": "http://localhost:8000",
            "/auth": "http://localhost:8000",
        },
    },
});
