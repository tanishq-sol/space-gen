import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"SF Pro Text"', '"Segoe UI Variable"', 'system-ui', 'sans-serif'],
        display: ['var(--font-display)', '-apple-system', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
      },
      colors: {
        // Light palette (DESIGN.md). Semantic names first, legacy names remapped below.
        vellum: "#F5F7FA",
        paper: "#FFFFFF",
        ink: "#0B1F3A",
        navy: "#1B3A6B",
        slate: "#4D6080",
        hairline: "#DDE3EC",

        background: "#F5F7FA",
        surface: "#FFFFFF",
        "surface-elevated": "#EEF2F7",
        "surface-hover": "#E6EBF2",
        border: "#DDE3EC",
        "border-subtle": "#E9EDF3",

        "text-primary": "#0B1F3A",
        "text-secondary": "#4D6080",
        "text-muted": "#5E6F8A",

        accent: {
          DEFAULT: "#1B3A6B",
          light: "#2D5290",
          dark: "#12294F",
          muted: "#1B3A6B1A",
        },

        success: { DEFAULT: "#067647", muted: "#0676471A" },
        warning: { DEFAULT: "#B54708", muted: "#B547081A" },
        error: { DEFAULT: "#B42318", muted: "#B423181A" },
        info: { DEFAULT: "#175CD3", muted: "#175CD31A" },
      },
      boxShadow: {
        'float': '0 8px 32px rgba(11, 31, 58, 0.12)',
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(ellipse at center, var(--tw-gradient-stops))',
      },
      borderRadius: {
        control: '8px',
        panel: '14px',
        sheet: '18px',
        '2xl': '1rem',
        '3xl': '1.5rem',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-down': 'slideDown 0.3s ease-out',
        'scale-in': 'scaleIn 0.2s ease-out',
        'shimmer': 'shimmer 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideDown: {
          '0%': { opacity: '0', transform: 'translateY(-8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
    },
  },
  plugins: [],
};
export default config;
