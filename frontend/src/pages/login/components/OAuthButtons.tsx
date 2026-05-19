import { useEffect, useState } from 'react'
import { Button, Divider, Space } from 'antd'
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
    <div className="login-oauth">
      <Divider>企业身份登录</Divider>
      <Space direction="vertical" style={{ width: '100%' }}>
        {providers.map((provider) => (
          <Button
            key={provider.name}
            block
            size="large"
            icon={<img className="login-button-icon" src="/favicon.svg" alt="" />}
            onClick={() => handleClick(provider)}
          >
            {provider.displayName}
          </Button>
        ))}
      </Space>
    </div>
  )
}
