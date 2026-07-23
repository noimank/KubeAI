import { api } from './api'
import type { BaseResponse, PageData } from '@/types/api'
import type {
  DbConnection,
  DbConnectionCreate,
  DbConnectionUpdate,
  QueryResult,
  QueryRequest,
  SaveResultRequest,
  TableInfo,
  ColumnInfo,
  TestResult,
} from '@/types/dataExplore'

// ---- 连接管理 ----

export async function getDbConnections(
  page = 1,
  pageSize = 20,
  search?: string,
): Promise<PageData<DbConnection>> {
  const params: Record<string, unknown> = { page, page_size: pageSize }
  if (search) params.search = search
  const res = await api.get<BaseResponse<PageData<DbConnection>>>('/db-connections', { params })
  return res.data.data!
}

export async function getDbConnection(id: string): Promise<DbConnection> {
  const res = await api.get<BaseResponse<DbConnection>>(`/db-connections/${id}`)
  return res.data.data!
}

export async function createDbConnection(data: DbConnectionCreate): Promise<DbConnection> {
  const res = await api.post<BaseResponse<DbConnection>>('/db-connections', data)
  return res.data.data!
}

export async function updateDbConnection(
  id: string,
  data: DbConnectionUpdate,
): Promise<DbConnection> {
  const res = await api.put<BaseResponse<DbConnection>>(`/db-connections/${id}`, data)
  return res.data.data!
}

export async function deleteDbConnection(id: string): Promise<void> {
  await api.delete(`/db-connections/${id}`)
}

export async function testConnection(id: string): Promise<TestResult> {
  const res = await api.post<BaseResponse<TestResult>>(`/db-connections/${id}/test`)
  return res.data.data!
}

// ---- 查询执行 ----

export async function executeQuery(data: QueryRequest): Promise<QueryResult> {
  const res = await api.post<BaseResponse<QueryResult>>('/query-results/execute', data)
  return res.data.data!
}

// ---- Schema 浏览 ----

export async function listTables(connectionId: string): Promise<TableInfo[]> {
  const res = await api.get<BaseResponse<TableInfo[]>>(`/query-results/tables/${connectionId}`)
  return res.data.data!
}

export async function getTableSchema(
  connectionId: string,
  tableName: string,
  tableSchema?: string,
): Promise<ColumnInfo[]> {
  const params: Record<string, unknown> = {}
  if (tableSchema) params.table_schema = tableSchema
  const res = await api.get<BaseResponse<ColumnInfo[]>>(
    `/query-results/tables/${connectionId}/${tableName}/schema`,
    { params },
  )
  return res.data.data!
}

// ---- 保存结果 ----

export async function saveQueryResult(
  data: SaveResultRequest,
): Promise<{ path: string; rows: number }> {
  const res = await api.post<BaseResponse<{ path: string; rows: number }>>(
    '/query-results/save',
    data,
  )
  return res.data.data!
}
