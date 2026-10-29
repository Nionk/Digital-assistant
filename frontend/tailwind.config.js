/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#F6F5F0",
        surface: {
          DEFAULT: "#FFFFFF",
          muted: "#EFECE6",
          hover: "#F3F1EB",
        },
        border: {
          DEFAULT: "#E5E3DC",
          strong: "#D2CFC5",
        },
        ink: {
          DEFAULT: "#18181B",
          secondary: "#4A4843",
          muted: "#686660",
          faint: "#9A978E",
        },
        pine: {
          DEFAULT: "#16382C",
          hover: "#1E4B3B",
          deep: "#0F291F",
          light: "#235342",
        },
        sage: {
          DEFAULT: "#2D6A4F",
          tint: "#E8F3EF",
          border: "#B7DFD0",
        },
        terracotta: {
          DEFAULT: "#C85A32",
          hover: "#B04B25",
          tint: "#FFF7ED",
          border: "#F5D0B5",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      boxShadow: {
        card: "0 1px 3px 0 rgba(24, 24, 27, 0.04), 0 1px 2px -1px rgba(24, 24, 27, 0.03)",
        elevated:
          "0 10px 25px -5px rgba(22, 56, 44, 0.08), 0 8px 10px -6px rgba(22, 56, 44, 0.04)",
        drawer: "-8px 0 32px rgba(24, 24, 27, 0.12)",
      },
      borderRadius: {
        card: "12px",
        control: "8px",
        badge: "6px",
      },
    },
  },
  plugins: [],
};

