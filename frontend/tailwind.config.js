/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        vmd: {
          bg: '#000000',
          elevated: '#0b0b0b',
          surface: 'rgba(8, 8, 8, 0.43)',
          surfaceStrong: 'rgba(11, 11, 11, 0.95)',
          surfaceSubtle: 'rgba(20, 24, 40, 0.38)',
          border: 'rgba(255, 255, 255, 0.08)',
          borderStrong: 'rgba(255, 255, 255, 0.18)',
          text: '#e5e7eb',
          textStrong: '#f5f5f5',
          textMuted: '#9ca3af',
          textSubtle: '#6b7280',
          link: '#d4d4d8',
          success: '#86efac',
          danger: '#fca5a5',
        },
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      boxShadow: {
        vmdCard: '0 8px 24px 0 rgba(0, 0, 0, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.18)',
        vmdCardHover: '0 10px 28px 0 rgba(0, 0, 0, 0.26), inset 0 1px 0 rgba(255, 255, 255, 0.2)',
        vmdGlass: '0 10px 30px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.14)',
        vmdChip: '0 2px 8px rgba(0, 0, 0, 0.2)',
      },
    },
  },
  plugins: [],
};
