import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      colors: {
        canvas: "#f6f3ec",
        ink: "#101828",
        mist: "#5f6b7d",
        cyan: {
          50: "#eefbff",
          100: "#d7f4fb",
          200: "#afe7f6",
          300: "#7fd1ee",
          400: "#32afd8",
          500: "#138bb6",
          600: "#0f6f93",
          700: "#105876",
          800: "#134860",
          900: "#163c4f"
        },
        coral: {
          50: "#fff6ec",
          100: "#ffe9cc",
          200: "#ffd199",
          300: "#ffb168",
          400: "#ff9039",
          500: "#f87216",
          600: "#d75a0d",
          700: "#ae430e",
          800: "#8d3713",
          900: "#742f14"
        }
      },
      boxShadow: {
        panel: "0 18px 45px rgba(16, 24, 40, 0.08)",
        float: "0 24px 70px rgba(16, 24, 40, 0.16)"
      },
      borderRadius: {
        "4xl": "2rem"
      },
      fontFamily: {
        sans: ["Avenir Next", "Segoe UI Variable", "Segoe UI", "sans-serif"]
      }
    }
  },
  plugins: []
};

export default config;
