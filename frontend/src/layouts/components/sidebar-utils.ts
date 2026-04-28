export interface MenuItem {
  path: string
  name: string
  icon: React.ReactNode
  permission?: string
  children?: MenuItem[]
}

export function filterMenuItems(
  items: MenuItem[],
  hasPermission: (p: string) => boolean,
): MenuItem[] {
  return items
    .map((item) => {
      if (item.children) {
        const filteredChildren = filterMenuItems(item.children, hasPermission)
        if (filteredChildren.length === 0) return null
        return { ...item, children: filteredChildren }
      }
      if (item.permission && !hasPermission(item.permission)) return null
      return item
    })
    .filter((item): item is MenuItem => item !== null)
}

export function toMenuDataItem(item: MenuItem): Record<string, unknown> {
  const result: Record<string, unknown> = {
    path: item.path,
    name: item.name,
    icon: item.icon,
  }
  if (item.children) {
    result.children = item.children.map(toMenuDataItem)
  }
  return result
}
