import { describe, it, expect, vi, beforeEach } from 'vitest'

const apiPost = vi.fn()

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: (...args: unknown[]) => apiPost(...args),
    delete: vi.fn(),
  },
}))

import { pauseTuningStudy, resumeTuningStudy, stopTuningStudy } from '@/services/tuning'

describe('tuning service', () => {
  beforeEach(() => {
    apiPost.mockReset()
    apiPost.mockResolvedValue({ data: { data: { id: 'study-1', status: 'running' } } })
  })

  it('pauseTuningStudy POSTs to /pause', async () => {
    await pauseTuningStudy('study-1')
    expect(apiPost).toHaveBeenCalledWith('/tuning/studies/study-1/pause')
  })

  it('resumeTuningStudy POSTs to /resume', async () => {
    await resumeTuningStudy('study-1')
    expect(apiPost).toHaveBeenCalledWith('/tuning/studies/study-1/resume')
  })

  it('stopTuningStudy POSTs to /stop', async () => {
    await stopTuningStudy('study-1')
    expect(apiPost).toHaveBeenCalledWith('/tuning/studies/study-1/stop')
  })

  it('returns the wrapped data payload', async () => {
    const result = await pauseTuningStudy('study-1')
    expect(result).toEqual({ id: 'study-1', status: 'running' })
  })
})
