/**
 * 复制文本到剪贴板。navigator.clipboard 仅在安全上下文（HTTPS 或 localhost）暴露，
 * HTTP 部署下为 undefined，回落到隐藏 textarea + execCommand('copy')。
 * 返回是否复制成功，调用方据此提示，不要在成功前预弹成功 toast。
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  if (navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // 权限被拒等异常时落到 execCommand 兜底
    }
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  // WORKAROUND(execCommand 已弃用): HTTP 非安全上下文无 navigator.clipboard, execCommand 是唯一可用复制途径(MDN 认可的遗留场景); 上 HTTPS 后此兜底可整体删除
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  document.body.removeChild(textarea)
  return ok
}
