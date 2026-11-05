/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0f7ff',
          100: '#e0effe',
          200: '#bae0fd',
          300: '#7cc7fc',
          400: '#36abf8',
          500: '#0c8de8',
          600: '#006fc5',
          700: '#01589f',
          800: '#064b83',
          900: '#0b3f6d',
        },
      },
    },
  },
  plugins: [],
};
