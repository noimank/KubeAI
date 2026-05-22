export type EnvironmentType = 'jupyter' | 'vscode' | 'rstudio'

export const ENVIRONMENT_TYPE_LABELS: Record<EnvironmentType, string> = {
  jupyter: 'Jupyter Notebook',
  vscode: 'VS Code',
  rstudio: 'RStudio',
}

export const ENVIRONMENT_TYPE_COLORS: Record<EnvironmentType, string> = {
  jupyter: 'orange',
  vscode: 'blue',
  rstudio: 'purple',
}

export interface DevEnvironmentImage {
  id: string
  name: string
  environmentType: EnvironmentType
  imageRef: string
  description?: string
  icon?: string
  defaultCpu: string
  defaultMemory: string
  defaultGpuCount: number
  isEnabled: boolean
  tenantId?: string
  createdAt: string
  updatedAt: string
}

export interface DevEnvironmentImageCreateParams {
  name: string
  environmentType: EnvironmentType
  imageRef: string
  description?: string
  icon?: string
  defaultCpu?: string
  defaultMemory?: string
  defaultGpuCount?: number
}

export interface DevEnvironmentImageUpdateParams {
  name?: string
  environmentType?: EnvironmentType
  imageRef?: string
  description?: string
  icon?: string
  defaultCpu?: string
  defaultMemory?: string
  defaultGpuCount?: number
}

export interface DevEnvironmentImageSelectable {
  id: string
  name: string
  environmentType: EnvironmentType
  imageRef: string
  icon?: string
  defaultCpu: string
  defaultMemory: string
  defaultGpuCount: number
}
