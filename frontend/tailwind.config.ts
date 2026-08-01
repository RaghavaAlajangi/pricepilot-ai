import type { Config } from "tailwindcss";

/** Dark dashboard theme — tokens mirror the validated chart palette. */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        page: "#0d0d0d", // page plane
        surface: "#1a1a19", // card / chart surface
        raised: "#232322", // hover & tooltip surface
        ink: {
          DEFAULT: "#ffffff", // primary
          secondary: "#c3c2b7",
          muted: "#898781",
        },
        line: "#2c2c2a", // hairline grid
        accent: {
          DEFAULT: "#3987e5", // blue, categorical slot 1 (dark step)
          deep: "#1c5cab",
        },
        status: {
          good: "#0ca30c",
          warning: "#fab219",
          critical: "#d03b3b",
        },
      },
    },
  },
  plugins: [],
};

export default config;
