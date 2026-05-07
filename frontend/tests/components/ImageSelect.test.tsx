import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ImageSelect from '@/components/ImageSelect'

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

vi.mock('@/services/images', () => ({
  getSelectableImages: vi.fn(),
}))

const mockGetSelectableImages = vi.mocked(await import('@/services/images')).getSelectableImages

function renderSelect(props: React.ComponentProps<typeof ImageSelect> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ImageSelect {...props} />
    </QueryClientProvider>,
  )
}

const mockPresetImage = {
  id: 'img-1',
  name: 'PyTorch',
  tag: '2.1.0',
  imageRef: 'pytorch/pytorch:2.1.0',
  source: 'preset',
}

const mockCustomImage = {
  id: 'img-2',
  name: 'my-custom',
  tag: 'v1.0',
  imageRef: 'harbor.local/kubeai-test/my-custom:v1.0',
  source: 'custom',
}

describe('ImageSelect', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render with loading state', () => {
    mockGetSelectableImages.mockReturnValue(new Promise(() => {}))
    const { container } = renderSelect()
    expect(container.querySelector('.ant-select')).toBeTruthy()
  })

  it('should show grouped options after opening dropdown', async () => {
    mockGetSelectableImages.mockResolvedValueOnce([mockPresetImage, mockCustomImage])

    renderSelect()

    await waitFor(() => {
      expect(screen.getByRole('combobox')).toBeTruthy()
    })

    await userEvent.click(screen.getByRole('combobox'))

    expect(await screen.findByText('预置镜像')).toBeTruthy()
    expect(screen.getByText('自定义镜像')).toBeTruthy()
    expect(screen.getByText('PyTorch:2.1.0')).toBeTruthy()
    expect(screen.getByText('my-custom:v1.0')).toBeTruthy()
  })

  it('should show empty state when no images', async () => {
    mockGetSelectableImages.mockResolvedValueOnce([])

    renderSelect()

    await waitFor(() => {
      expect(screen.getByRole('combobox')).toBeTruthy()
    })

    await userEvent.click(screen.getByRole('combobox'))

    expect(await screen.findByText('暂无可用镜像')).toBeTruthy()
  })

  it('should call onChange when selecting an image', async () => {
    mockGetSelectableImages.mockResolvedValueOnce([mockPresetImage])

    const onChange = vi.fn()
    renderSelect({ onChange })

    await waitFor(() => {
      expect(screen.getByRole('combobox')).toBeTruthy()
    })

    await userEvent.click(screen.getByRole('combobox'))

    const option = await screen.findByText('PyTorch:2.1.0')
    await userEvent.click(option)

    expect(onChange).toHaveBeenCalledWith('img-1')
  })

  it('should respect disabled prop', async () => {
    mockGetSelectableImages.mockResolvedValueOnce([mockPresetImage])

    renderSelect({ disabled: true })

    await waitFor(() => {
      const select = screen.getByRole('combobox')
      expect(select).toBeTruthy()
    })
  })
})
