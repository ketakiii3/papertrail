import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          400: "#38bdf8",
          500: "#0c8aff",
          600: "#2563eb",
        },
      },
    },
  },
  plugins: [],
};

export default config;
