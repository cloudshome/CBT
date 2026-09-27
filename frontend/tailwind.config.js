/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: {
          DEFAULT: '#0B0E14',
          subtle: '#10141D',
          card: '#161B26',
          hover: '#1D2433',
        },
        border: {
          DEFAULT: '#232B3E',
          active: '#3A4763',
        },
        terminal: {
          green: '#00FF9D',
          cyan: '#00F0FF',
          red: '#FF3B69',
          amber: '#FFB800',
          purple: '#B026FF',
          muted: '#8A99AD',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Menlo', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
