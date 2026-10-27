/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        finn: {
          bg: "#0A0A0F",
          surface: "#12121A",
          card: "#1A1A25",
          border: "#2A2A3A",
          muted: "#6B7280",
          text: "#E5E7EB",
          accent: "#3B82F6",
          green: "#22C55E",
          red: "#EF4444",
          amber: "#F59E0B",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "system-ui",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "SF Mono", "monospace"],
      },
      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "0.875rem" }],
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
