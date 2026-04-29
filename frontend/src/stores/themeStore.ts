import { create } from 'zustand'

const THEME_KEY = 'kubeai_theme'

type ThemeMode = 'light' | 'dark'

function getStoredTheme(): ThemeMode {
  const stored = localStorage.getItem(THEME_KEY)
  if (stored === 'dark' || stored === 'light') return stored
  return 'light'
}

function applyTheme(mode: ThemeMode) {
  document.documentElement.dataset.theme = mode
}

interface ThemeState {
  themeMode: ThemeMode
  toggleTheme: () => void
}

export const useThemeStore = create<ThemeState>((set) => {
  const initial = getStoredTheme()
  applyTheme(initial)

  return {
    themeMode: initial,

    toggleTheme: () =>
      set((state) => {
        const next = state.themeMode === 'light' ? 'dark' : 'light'
        localStorage.setItem(THEME_KEY, next)
        applyTheme(next)
        return { themeMode: next }
      }),
  }
})
