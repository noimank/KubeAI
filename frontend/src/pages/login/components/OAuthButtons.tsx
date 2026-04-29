import { useEffect, useState } from 'react'
import { Button, Space } from 'antd'
import { getOAuthProviders } from '@/services/oauth'
import type { OAuthProvider } from '@/services/oauth'

export default function OAuthButtons() {
  const [providers, setProviders] = useState<OAuthProvider[]>([])

  useEffect(() => {
    getOAuthProviders().then((res) => {
      if (res.success && res.data) {
        setProviders(res.data)
      }
    })
  }, [])

  if (providers.length === 0) return null

  const handleClick = (provider: OAuthProvider) => {
    window.location.href = `/api/auth/oauth/${provider.name}/authorize`
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      {providers.map((provider) => (
        <Button key={provider.name} block size="large" onClick={() => handleClick(provider)}>
          {provider.displayName}
        </Button>
      ))}
    </Space>
  )
}
