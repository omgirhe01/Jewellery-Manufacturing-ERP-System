/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        gold: { DEFAULT: '#C9A84C', light: '#e8d89a', dark: '#8B6914', dim: '#8a6a2a' },
        erp: {
          bg: '#0e0d0b',
          card: '#13110e',
          hover: '#1e1a14',
          border: '#2a2318',
          'border-light': '#1a1612',
          'text-primary': '#e8e0d0',
          'text-secondary': '#8a7a5a',
          'text-muted': '#5a4a2a',
        }
      },
      fontFamily: {
        mono: ['DM Mono', 'Courier New', 'monospace'],
        serif: ['Cormorant Garamond', 'Georgia', 'serif'],
      }
    },
  },
  plugins: [],
}
