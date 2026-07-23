export type DbType = 'postgresql' | 'mysql' | 'spark' | 'hive' | 'mssql' | 'doris'

export interface DbConnection {
  id: string
  name: string
  dbType: DbType
  host: string
  port: number
  databaseName: string
  username: string
  extraParams?: string
  description?: string
  createdBy: string
  tenantId: string
  createdAt: string
  updatedAt: string
}

export interface DbConnectionCreate {
  name: string
  dbType: DbType
  host: string
  port: number
  databaseName: string
  username: string
  password: string
  extraParams?: string
  description?: string
}

export interface DbConnectionUpdate {
  name?: string
  dbType?: DbType
  host?: string
  port?: number
  databaseName?: string
  username?: string
  password?: string
  extraParams?: string
  description?: string
}

export interface QueryResult {
  columns: string[]
  rows: unknown[][]
  rowCount: number
  truncated: boolean
  executionTimeMs: number
}

export interface QueryRequest {
  connectionId: string
  sql: string
  maxRows?: number
  timeout?: number
}

export interface SaveResultRequest {
  connectionId: string
  sql: string
  targetPath: string
  filename: string
  format: 'csv' | 'json'
}

export interface TableInfo {
  name: string
  tableSchema?: string | null
  type: 'table' | 'view'
}

export interface ColumnInfo {
  name: string
  dataType: string
  nullable: boolean
  isPrimaryKey?: boolean
  defaultValue?: string | null
  comment?: string | null
}

export interface TestResult {
  success: boolean
  message: string
}

export const DB_TYPE_LABELS: Record<DbType, string> = {
  postgresql: 'PostgreSQL',
  mysql: 'MySQL',
  spark: 'Spark',
  hive: 'Hive',
  mssql: 'SQL Server',
  doris: 'Doris',
}

export const DB_DEFAULT_PORTS: Record<DbType, number> = {
  postgresql: 5432,
  mysql: 3306,
  spark: 10000,
  hive: 10000,
  mssql: 1433,
  doris: 9030,
}
