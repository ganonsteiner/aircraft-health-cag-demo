import path from "node:path";
import { fileURLToPath } from "node:url";
import typography from "@tailwindcss/typography";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    path.join(__dirname, "index.html"),
    path.join(__dirname, "src/**/*.{js,ts,jsx,tsx}"),
  ],
  theme: {
    extend: {
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', "Consolas", "monospace"],
      },
      colors: {
        // Cognite primary blue
        primary: {
          DEFAULT: "#304cb2",
          foreground: "#ffffff",
        },
        // shadcn CSS-variable-based color aliases
        background: "var(--background)",
        foreground: "var(--foreground)",
        canvas: "var(--canvas)",
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        border: "var(--border)",
        ring: "var(--ring)",
      },
      borderRadius: {
        lg: "0.75rem",
        md: "0.5rem",
        sm: "0.375rem",
      },
    },
  },
  plugins: [typography],
};
