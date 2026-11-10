/** @type {import('tailwindcss').Config} */
// Color tokens sourced from design/tokens.json — run design/generate-colorsets.py to sync macOS app colors
import { tokens, tokenVariables } from './tokens.js'

export default {
  content: [
    './index.html',
    './src/**/*.{js,ts}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Helvetica', 'Arial', 'sans-serif'],
        mono: ['"SF Mono"', '"Fira Code"', 'Consolas', 'monospace'],
      },
      colors: {
        // "amber" key kept so existing section classes (text-amber-400, bg-amber-500/x) pick up the new neon values
        amber: {
          300: tokens.colors['accent-lighter'],
          400: tokens.colors['accent-light'],
          500: tokens.colors['accent'],
        },
        neon: {
          pink:   tokens.colors['neon-pink'],
          yellow: tokens.colors['neon-yellow'],
          cyan:   tokens.colors['neon-cyan'],
          purple: tokens.colors['neon-purple'],
        },
        neutral: {
          850: tokens.colors['bg-elevated'],
          925: tokens.colors['bg-secondary'],
          950: tokens.colors['bg-primary'],
        },
      },
      keyframes: {
        'fade-up': {
          '0%':   { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.5s ease-out forwards',
      },
    },
  },
  plugins: [tokenVariables],
}
