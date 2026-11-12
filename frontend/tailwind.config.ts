import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1c1915",
        paper: "#f3efe6",
        card: "#fffdf8",
        line: "#e4d9c8",
        amber: "#c9841a",
        pine: "#1f6b45",
        brick: "#a33b2b",
        tide: "#2c4a5e",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 1px 0 rgba(28,25,21,0.04), 0 12px 30px rgba(28,25,21,0.05)",
      },
    },
  },
  plugins: [],
};

export default config;
