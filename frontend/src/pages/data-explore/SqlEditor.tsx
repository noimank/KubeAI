/**
 * SQL 编辑器：CodeMirror 6 本地打包。
 *
 * 页面仅需 SQL 语法高亮与基础编辑（行号/换行/撤销/查找）。此前用 Monaco 过重
 * （gzip ~1MB 且大版本升级成本高，0.56 即发生过结构重构），CodeMirror 6 体积
 * 约为其 1/10，功能面与本页需求对齐。纯内网部署无任何外网资源依赖。
 */
import { sql } from '@codemirror/lang-sql'
import CodeMirror, { EditorView } from '@uiw/react-codemirror'

interface Props {
  value: string
  onChange: (value: string) => void
}

export default function SqlEditor({ value, onChange }: Props) {
  return (
    <CodeMirror
      value={value}
      onChange={onChange}
      height="100%"
      style={{ height: '100%', fontSize: 14 }}
      extensions={[sql(), EditorView.lineWrapping]}
      basicSetup={{
        foldGutter: false,
        autocompletion: false,
        highlightActiveLine: false,
        highlightActiveLineGutter: false,
      }}
    />
  )
}
