/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        serif: ['"Cormorant Garamond"', 'Georgia', 'serif'],
      },
      colors: {
        warm: {
          50: "#0a0908",
          100: "#12100e",
          200: "#1c1915",
          300: "#2a2620",
          400: "#3d3830",
          500: "#6b6154",
          600: "#8c7e6a",
          700: "#a89b88",
          800: "#c9b8a4",
          900: "#e0d8cc",
          950: "#f5f2ec",
        },
        accent: {
          50: "#1a1508",
          100: "#2a2210",
          200: "#3d3218",
          300: "#5c4a1f",
          400: "#9a7a28",
          500: "#c49a20",
          600: "#d4ae44",
          700: "#e0c066",
          800: "#e8d088",
          900: "#f0e4b8",
        },
        severity: {
          critical: "#C2423E",
          high: "#C27830",
          medium: "#A89032",
          low: "#4A8B5C",
        },
      },
    },
  },
  plugins: [],
};
