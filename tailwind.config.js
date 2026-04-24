/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./home/templates/**/*.html",
    "./blog/templates/**/*.html",
    "./search/templates/**/*.html",
    "./config/templates/**/*.html",
    "./home/static/**/*.js",
  ],
  safelist: [
    "ky-page",
    "ky-surface",
    "ky-surface-muted",
    "ky-title",
    "ky-kicker",
    "ky-link",
    "ky-button-primary",
    "ky-button-secondary",
    "ky-badge",
    "ky-border",
  ],
  theme: {
    extend: {
      // Brand and interface color tokens.
      colors: {
        brand: {
          DEFAULT: "#66f1d2",
          strong: "#43dfbe",
          soft: "#c8fbef",
        },
        secondary: {
          DEFAULT: "#2f5fd0",
          strong: "#1f3f7a",
          soft: "#dbe5ff",
        },
        accent: {
          DEFAULT: "#d97b2d",
          soft: "#e6a34a",
        },
        tertiary: "#c44536",
        bg: {
          DEFAULT: "#eef3f1",
          soft: "#f6faf8",
        },
        surface: {
          DEFAULT: "#ffffff",
          muted: "#e5eeeb",
        },
        text: {
          DEFAULT: "#1f2933",
          muted: "#61717b",
          soft: "#7b8b94",
        },
        border: {
          DEFAULT: "#dbe5e1",
          strong: "#b8c7c1",
        },
        success: "#2d8f6f",
        warning: "#b7791f",
        danger: "#c44536",
      },
      // Kýrauga typography tokens.
      fontFamily: {
        display: ['"AXIS-ExtraBold"', '"Arial Black"', "sans-serif"],
        body: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      // Shared shape tokens.
      borderRadius: {
        sm: "0.375rem",
        md: "0.75rem",
        lg: "1.25rem",
        xl: "1.75rem",
        "2xl": "2.5rem",
      },
      // Soft landscape-inspired elevation tokens.
      boxShadow: {
        soft: "0 8px 30px rgba(31, 41, 51, 0.08)",
        card: "0 12px 40px rgba(31, 41, 51, 0.12)",
      },
      // Layout spacing aliases for repeated page rhythm.
      spacing: {
        page: "1.5rem",
        section: "4rem",
        "section-lg": "6rem",
      },
    },
  },
  plugins: [],
};
