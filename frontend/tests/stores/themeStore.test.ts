import { describe, it, expect, beforeEach } from 'vitest'
import { useThemeStore } from '@/stores/themeStore'

describe('themeStore', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    useThemeStore.setState({ themeMode: 'light' })
    useThemeStore.getState().toggleTheme()
    useThemeStore.getState().toggleTheme()
  })

  it('初始状态应为 light', () => {
    expect(useThemeStore.getState().themeMode).toBe('light')
  })

  it('toggleTheme 应切换到 dark', () => {
    useThemeStore.getState().toggleTheme()
    expect(useThemeStore.getState().themeMode).toBe('dark')
  })

  it('再次 toggleTheme 应切换回 light', () => {
    useThemeStore.getState().toggleTheme()
    useThemeStore.getState().toggleTheme()
    expect(useThemeStore.getState().themeMode).toBe('light')
  })

  it('切换时持久化到 localStorage', () => {
    useThemeStore.getState().toggleTheme()
    expect(localStorage.getItem('kubeai_theme')).toBe('dark')
    useThemeStore.getState().toggleTheme()
    expect(localStorage.getItem('kubeai_theme')).toBe('light')
  })

  it('切换时设置 document.documentElement.dataset.theme', () => {
    useThemeStore.getState().toggleTheme()
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('连续切换保持 DOM 和 localStorage 同步', () => {
    const { toggleTheme } = useThemeStore.getState()
    toggleTheme()
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('kubeai_theme')).toBe('dark')

    toggleTheme()
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(localStorage.getItem('kubeai_theme')).toBe('light')

    toggleTheme()
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(useThemeStore.getState().themeMode).toBe('dark')
  })
})
