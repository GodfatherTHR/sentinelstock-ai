import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        shell: "#071014",
        panel: "#10242A",
        seam: "#22434A",
        ink: "#E9F3EF",
        muted: "#8EA7A6",
        mint: "#8BE4C0",
        orange: "#FF9C58",
        coral: "#FF6B62",
        ice: "#8CD8EA",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular"],
      },
      boxShadow: { glow: "0 0 28px rgba(139, 228, 192, 0.12)" },
    },
  },
  plugins: [],
};

export default config;
