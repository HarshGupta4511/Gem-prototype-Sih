/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Institutional deep-navy palette — "GeM Compliance Intelligence".
        // Restrained, official, trustworthy. Light interface; navy is used for
        // structure (sidebar, headers, primary actions), never whole-page dark.
        brand: {
          50: '#f1f5fa',
          100: '#e2eaf3',
          200: '#c3d4e8',
          300: '#9ab4d6',
          400: '#688cbe',
          500: '#466fa5',
          600: '#33578a',
          700: '#2a4570',
          800: '#1f3a5f',
          900: '#16294a',
          950: '#0d1b33',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px 0 rgb(15 23 42 / 0.05), 0 1px 3px 0 rgb(15 23 42 / 0.06)',
        panel: '0 1px 2px 0 rgb(15 23 42 / 0.04)',
      },
    },
  },
  plugins: [],
};
