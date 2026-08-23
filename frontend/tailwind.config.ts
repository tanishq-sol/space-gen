import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: "#0A0A0A",
        surface: "#141414",
        "surface-elevated": "#1E1E1E",
        border: "#2A2A2A",
        "text-primary": "#FAFAFA",
        "text-secondary": "#888888",
        accent: "#6366F1",
        success: "#22C55E",
        warning: "#F59E0B",
      },
    },
  },
  plugins: [],
};
export default config;
