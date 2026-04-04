/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', "Consolas", "monospace"],
      },
      colors: {
        zinc: {
          950: "#09090b",
        },
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
