import { Outlet } from 'react-router-dom'

export default function AuthLayout() {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        background: '#f0f2f5',
      }}
    >
      <Outlet />
    </div>
  )
}
