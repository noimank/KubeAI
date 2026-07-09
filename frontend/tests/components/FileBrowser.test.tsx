import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import FileBrowser from '@/components/FileBrowser'
import type { FsBrowseResponse } from '@/services/filesystem'

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

vi.mock('@/services/filesystem', () => ({
  browseFilesystem: vi.fn(),
}))

const { browseFilesystem } = (await import('@/services/filesystem')) as unknown as {
  browseFilesystem: ReturnType<typeof vi.fn>
}

const HOME_ROOT = '/kubeai/home/alice'
const WS_ROOT = '/kubeai/workspace/acme'
const README = `${HOME_ROOT}/README.md`
const EXP_1 = `${HOME_ROOT}/exp-1`
const MODEL = `${HOME_ROOT}/exp-1/model.bin`

function fixtures(): Record<string, FsBrowseResponse> {
  return {
    [HOME_ROOT]: {
      path: HOME_ROOT,
      truncated: false,
      entries: [
        { name: 'exp-1', path: EXP_1, type: 'directory' },
        { name: 'README.md', path: README, type: 'file', sizeBytes: 12 },
      ],
    },
    [EXP_1]: {
      path: EXP_1,
      truncated: false,
      entries: [{ name: 'model.bin', path: MODEL, type: 'file', sizeBytes: 4096 }],
    },
    [WS_ROOT]: {
      path: WS_ROOT,
      truncated: false,
      entries: [],
    },
  }
}

function setupMocks() {
  const dict = fixtures()
  browseFilesystem.mockImplementation(async (path: string) => {
    const key = path in dict ? path : path.replace(/\/$/, '')
    const resp = dict[key]
    if (!resp) throw new Error(`unexpected path ${path}`)
    return resp
  })
}

function renderBrowser(props: Partial<React.ComponentProps<typeof FileBrowser>> = {}) {
  const onChange = props.onChange ?? vi.fn()
  const utils = render(
    <FileBrowser
      value={props.value ?? []}
      onChange={onChange}
      roots={props.roots ?? [HOME_ROOT, WS_ROOT]}
      {...props}
    />,
  )
  return { ...utils, onChange }
}

/** 点击 .ant-tree-switcher 在数组中的第 index 个. */
async function clickSwitcher(index: number) {
  // 每次重新查询 — Tree 在异步 loadData 后会重新渲染 children 与 switcher.
  await waitFor(() => {
    expect(document.querySelectorAll('.ant-tree-switcher').length).toBeGreaterThan(index)
  })
  const switchers = document.querySelectorAll('.ant-tree-switcher')
  await userEvent.click(switchers[index] as HTMLElement)
}

/** 点击 .ant-tree-checkbox 在数组中的第 index 个. */
async function clickCheckbox(index: number) {
  await waitFor(() => {
    expect(document.querySelectorAll('.ant-tree-checkbox').length).toBeGreaterThan(index)
  })
  const checkboxes = document.querySelectorAll('.ant-tree-checkbox')
  await userEvent.click(checkboxes[index] as HTMLElement)
}

describe('FileBrowser', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setupMocks()
  })

  it('renders the two virtual root nodes', async () => {
    renderBrowser()
    expect(await screen.findByText(HOME_ROOT)).toBeTruthy()
    expect(await screen.findByText(WS_ROOT)).toBeTruthy()
  })

  it('expands a root and loads its children on click', async () => {
    renderBrowser()
    await screen.findByText(HOME_ROOT)
    await clickSwitcher(0)
    await waitFor(() => {
      expect(browseFilesystem).toHaveBeenCalledWith(HOME_ROOT)
    })
    expect(await screen.findByText('exp-1')).toBeTruthy()
    expect(await screen.findByText('README.md')).toBeTruthy()
  })

  it('reports selected paths via onChange when checkbox toggled', async () => {
    const { onChange } = renderBrowser()
    await screen.findByText(HOME_ROOT)
    await clickSwitcher(0)
    await screen.findByText('README.md')
    // Tree 节点顺序: home root(checkbox=0), exp-1(1), README.md(2) — 点击 README.md.
    await clickCheckbox(2)
    await waitFor(() => {
      expect(onChange).toHaveBeenCalled()
    })
    const paths = onChange.mock.calls.flatMap((c) => c[0] as string[])
    expect(paths).toContain(README)
  })

  it('clears selected paths when 清空 is clicked', async () => {
    const { onChange } = renderBrowser({ value: [README] })
    // 清空按钮 always enabled when checkedKeys non-empty.
    await userEvent.click(screen.getByRole('button', { name: /清空/ }))
    expect(onChange).toHaveBeenCalledWith([])
  })

  it('shows empty hint when no roots provided', () => {
    renderBrowser({ roots: [] })
    expect(screen.getByText('暂无可浏览的目录')).toBeTruthy()
    expect(browseFilesystem).not.toHaveBeenCalled()
  })

  it('expands further when a directory is expanded recursively', async () => {
    renderBrowser()
    await screen.findByText(HOME_ROOT)
    await clickSwitcher(0)
    await screen.findByText('exp-1')
    // 0=home root, 1=exp-1, 2=ws root — 点击 exp-1 继续下钻.
    await clickSwitcher(1)
    await waitFor(() => {
      expect(browseFilesystem).toHaveBeenCalledWith(EXP_1)
    })
    expect(await screen.findByText('model.bin')).toBeTruthy()
  })
})
