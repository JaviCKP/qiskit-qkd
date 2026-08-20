import animate from 'tailwindcss-animate'

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: 'rgb(var(--color-background) / <alpha-value>)',
        surface: 'rgb(var(--color-surface) / <alpha-value>)',
        raised: 'rgb(var(--color-raised) / <alpha-value>)',
        overlay: 'rgb(var(--color-overlay) / <alpha-value>)',
        border: 'rgb(var(--color-border) / <alpha-value>)',
        'border-strong': 'rgb(var(--color-border-strong) / <alpha-value>)',
        cyan: 'rgb(var(--color-accent) / <alpha-value>)',
        'cyan-soft': 'rgb(var(--color-accent-soft) / <alpha-value>)',
        violet: 'rgb(var(--color-violet) / <alpha-value>)',
        success: 'rgb(var(--color-success) / <alpha-value>)',
        warning: 'rgb(var(--color-warning) / <alpha-value>)',
        danger: 'rgb(var(--color-danger) / <alpha-value>)',
        chart: {
          1: 'rgb(var(--chart-1) / <alpha-value>)',
          2: 'rgb(var(--chart-2) / <alpha-value>)',
          3: 'rgb(var(--chart-3) / <alpha-value>)',
          4: 'rgb(var(--chart-4) / <alpha-value>)',
          5: 'rgb(var(--chart-5) / <alpha-value>)',
          6: 'rgb(var(--chart-6) / <alpha-value>)',
        },
      },
      fontFamily: {
        sans: ['Inter Variable', 'Inter', 'system-ui', 'Segoe UI', 'sans-serif'],
        mono: ['JetBrains Mono Variable', 'JetBrains Mono', 'ui-monospace', 'Consolas', 'monospace'],
      },
      fontSize: {
        // 12px floor for every label in the panel; dense scientific readouts
        // still need to be legible on a projector during the defence.
        '2xs': ['0.75rem', { lineHeight: '1.1rem' }],
      },
      letterSpacing: {
        eyebrow: '0.14em',
      },
      borderRadius: {
        panel: 'var(--radius-panel)',
        control: 'var(--radius-control)',
      },
      boxShadow: {
        focus: '0 0 0 3px rgb(var(--color-accent) / 0.22)',
        panel: '0 1px 2px rgb(0 0 0 / 0.4), 0 12px 32px -12px rgb(0 0 0 / 0.6)',
        lifted: '0 2px 4px rgb(0 0 0 / 0.4), 0 18px 40px -14px rgb(0 0 0 / 0.7)',
        glow: '0 0 0 1px rgb(var(--color-accent) / 0.25), 0 0 28px -6px rgb(var(--color-accent) / 0.45)',
      },
      backgroundImage: {
        'panel-sheen': 'linear-gradient(180deg, rgb(255 255 255 / 0.035), transparent 120px)',
        'grid-faint':
          'linear-gradient(rgb(var(--color-border) / 0.28) 1px, transparent 1px), linear-gradient(90deg, rgb(var(--color-border) / 0.28) 1px, transparent 1px)',
      },
      keyframes: {
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'none' },
        },
      },
      animation: {
        'fade-up': 'fade-up 260ms cubic-bezier(0.16, 1, 0.3, 1) both',
      },
      transitionTimingFunction: {
        emphasis: 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
    },
  },
  plugins: [animate],
}
