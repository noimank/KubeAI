import { useEffect, useRef, useState } from 'react'
import { Button, Space, Spin, Typography } from 'antd'
import { LeftOutlined, RightOutlined } from '@ant-design/icons'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl

/**
 * PDF 对象查看器 —— 用 pdfjs-dist v6 渲染当前页到 canvas，支持翻页。
 * v6 的 render 需要 `canvas`（非 canvasContext）；销毁走 loadingTask.destroy()。
 * 同源请求自动携带认证 Cookie。
 */
export default function PdfView({ value }: { value: unknown }) {
  const url = typeof value === 'string' ? value : ''
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const docRef = useRef<PDFDocumentProxy | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const [numPages, setNumPages] = useState(0)
  const [currentPage, setCurrentPage] = useState(1)

  // 加载文档
  useEffect(() => {
    if (!url) return
    let cancelled = false
    const loadingTask = pdfjsLib.getDocument({ url: url })
    setLoading(true)
    setError(false)
    loadingTask.promise
      .then((doc) => {
        if (cancelled) {
          void loadingTask.destroy()
          return
        }
        docRef.current = doc
        setNumPages(doc.numPages)
        setCurrentPage(1)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
      void loadingTask.destroy()
      docRef.current = null
    }
  }, [url])

  // 渲染当前页
  useEffect(() => {
    const doc = docRef.current
    const canvas = canvasRef.current
    if (!doc || !canvas || currentPage < 1) return
    let cancelled = false
    let renderTask: RenderTask | null = null
    void (async () => {
      setLoading(true)
      try {
        const page = await doc.getPage(currentPage)
        if (cancelled) return
        const viewport = page.getViewport({ scale: 1.5 })
        canvas.width = viewport.width
        canvas.height = viewport.height
        renderTask = page.render({ canvas, viewport })
        await renderTask.promise
      } catch {
        if (!cancelled) setError(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
      renderTask?.cancel()
    }
  }, [currentPage, numPages])

  if (!url) return <Typography.Text type="secondary">无 PDF 数据</Typography.Text>
  if (error) return <Typography.Text type="danger">PDF 加载失败</Typography.Text>

  return (
    <div style={{ marginBottom: 16 }}>
      {numPages > 0 && (
        <Space style={{ marginBottom: 8 }} align="center">
          <Button
            size="small"
            icon={<LeftOutlined />}
            disabled={currentPage <= 1}
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
          />
          <Typography.Text>
            {currentPage} / {numPages}
          </Typography.Text>
          <Button
            size="small"
            disabled={currentPage >= numPages}
            onClick={() => setCurrentPage((p) => Math.min(numPages, p + 1))}
          >
            <RightOutlined />
          </Button>
        </Space>
      )}
      <div style={{ position: 'relative', textAlign: 'center', overflow: 'auto', maxHeight: 600 }}>
        {loading && (
          <div style={{ padding: 48, display: 'flex', justifyContent: 'center' }}>
            <Spin />
          </div>
        )}
        <canvas
          ref={canvasRef}
          style={{ maxWidth: '100%', display: loading ? 'none' : 'inline-block' }}
        />
      </div>
    </div>
  )
}
