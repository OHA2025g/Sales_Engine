import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}", "../../packages/ui/src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "Inter", "system-ui", "sans-serif"],
      },
      colors: {
        canvas: "#0D1118",
        ink: "#EEF2FA",
        navy: "#EEF2FA",
        ivory: "#EEF2FA",
        sidebar: "#10151E",
        surface: "#151C27",
        raised: "#1B2432",
        azure: {
          DEFAULT: "#99A5FF",
          50: "#1B2432",
          100: "#20354D",
          200: "#9DCAFF",
          600: "#99A5FF",
          700: "#C5CCFF",
        },
        brand: {
          DEFAULT: "#99A5FF",
          50: "#1B2432",
          100: "#20354D",
          200: "#C5CCFF",
          600: "#C5CCFF",
          700: "#10151E",
        },
        gold: {
          DEFAULT: "#F3CB85",
          200: "#3D3223",
        },
        mint: "#8DD6B7",
      },
      boxShadow: {
        lift: "0 18px 44px rgba(0, 0, 0, 0.35)",
        glass: "0 16px 40px rgba(0, 0, 0, 0.28)",
      },
    },
  },
  plugins: [],
};

export default config;
