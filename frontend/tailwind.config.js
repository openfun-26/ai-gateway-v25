/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Public Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif']
      },
      colors: {
        accent: {
          DEFAULT: 'var(--accent)',
          soft: 'var(--accent-soft)',
          fg: 'var(--accent-fg)'
        },
        bg: 'var(--bg)',
        card: 'var(--card)',
        border2: 'var(--border)',
        muted: 'var(--muted)',
        content: 'var(--content)'
      },
      borderRadius: {
        card: '0.625rem'
      },
      boxShadow: {
        subtle: '0 1px 2px 0 rgb(0 0 0 / 0.04), 0 1px 3px 0 rgb(0 0 0 / 0.03)'
      }
    }
  },
  plugins: []
}
