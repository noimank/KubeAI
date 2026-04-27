import { Breadcrumb } from 'antd'
import { useLocation, useNavigate } from 'react-router-dom'
import { NAVIGATE_MAP } from '../MainLayout'

export function BreadcrumbNav() {
  const location = useLocation()
  const navigate = useNavigate()

  const paths = location.pathname.split('/').filter(Boolean)
  const items = [
    { title: <a onClick={() => navigate('/dashboard')}>首页</a> },
    ...paths.map((segment, index) => {
      const fullPath = '/' + paths.slice(0, index + 1).join('/')
      const name = NAVIGATE_MAP[fullPath] || segment
      const isLast = index === paths.length - 1
      return {
        title: isLast ? name : <a onClick={() => navigate(fullPath)}>{name}</a>,
      }
    }),
  ]

  return <Breadcrumb items={items} />
}
