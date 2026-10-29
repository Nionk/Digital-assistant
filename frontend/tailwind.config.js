/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#0B0E12",
        surface: {
          DEFAULT: "#161B22",
          muted: "#1A2028",
          hover: "#1E2530",
        },
        border: {
          DEFAULT: "#262D35",
          strong: "#38414F",
        },
        ink: {
          DEFAULT: "#F3F4F6",
          secondary: "#D1D5DB",
          muted: "#8E95A0",
          faint: "#636B78",
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
        novel: {
          sand: "#F4E8C1",
          sandLight: "#FBF6E9",
          sandBorder: "#E5D4A2",
          gold: "#E5C378",
          dark: "#0D1117",
          charcoal: "#161B22",
          slate: "#1F2430",
          border: "#2B3240",
          wine: "#5C1D24",
          wineTint: "#FCEBEF",
          emerald: "#0E382B",
          emeraldTint: "#E6F4EE",
        },
      },
      fontFamily: {
        sans: [
          '"Plus Jakarta Sans"',
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        serif: [
          "Lora",
          "Georgia",
          "Cambria",
          '"Times New Roman"',
          "serif",
        ],
        mono: [
          '"JetBrains Mono"',
          "monospace",
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
        badge: "3px",
        tag: "2px",
      },
    },
  },
  plugins: [],
};

