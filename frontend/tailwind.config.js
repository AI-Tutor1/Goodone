/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 50: "#f7f7f8", 200: "#d4d4d8", 700: "#3f3f46", 900: "#18181b" },
        accent: { 500: "#0d9488", 600: "#0b7c70" },
      },
    },
  },
  plugins: [],
};
