/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0a0e14",
        panel: "#111722",
        panel2: "#161e2b",
        border: "#1f2937",
        muted: "#64748b",
        text: "#e2e8f0",
        accent: "#3b82f6",
        ok: "#22c55e",
        warn: "#f59e0b",
        crit: "#ef4444",
      },
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
