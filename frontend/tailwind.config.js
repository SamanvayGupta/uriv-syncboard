/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy:  '#1a1a2e',
        panel: '#16213e',
        accent:'#0f3460',
        red:   '#e94560',
        teal:  '#0f8b8d',
      },
    },
  },
  plugins: [
    // prose plugin for ReactMarkdown
    require('@tailwindcss/typography'),
  ],
}
