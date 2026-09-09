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
                primary: '#409EFF',
                brand: {
                    50: '#ecf5ff',
                    100: '#d9ecff',
                    200: '#b3d8ff',
                    300: '#8cc5ff',
                    400: '#66b1ff',
                    500: '#409EFF',
                    600: '#3a8ee6',
                    700: '#337ecc',
                    800: '#2d6eb3',
                    900: '#265e99',
                },
            },
            keyframes: {
                'fade-in-up': {
                    '0%': { opacity: '0', transform: 'translateY(12px)' },
                    '100%': { opacity: '1', transform: 'translateY(0)' },
                },
                'fade-in-down': {
                    '0%': { opacity: '0', transform: 'translateY(-8px)' },
                    '100%': { opacity: '1', transform: 'translateY(0)' },
                },
                'fade-in': {
                    '0%': { opacity: '0' },
                    '100%': { opacity: '1' },
                },
                'scale-in': {
                    '0%': { opacity: '0', transform: 'scale(0.95)' },
                    '100%': { opacity: '1', transform: 'scale(1)' },
                },
            },
            animation: {
                'fade-in-up': 'fade-in-up 0.4s cubic-bezier(0.16, 1, 0.3, 1) both',
                'fade-in-down': 'fade-in-down 0.3s cubic-bezier(0.16, 1, 0.3, 1) both',
                'fade-in': 'fade-in 0.3s ease both',
                'scale-in': 'scale-in 0.3s cubic-bezier(0.16, 1, 0.3, 1) both',
            },
        },
    },
    plugins: [],
}
