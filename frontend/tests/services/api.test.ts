import { describe, it, expect } from 'vitest'
import { transformKeys, toCamelCase, toSnakeCase, SKIP_RECURSE_KEYS } from '@/services/api'

describe('toCamelCase', () => {
  it('should convert snake_case to camelCase', () => {
    expect(toCamelCase('hello_world')).toBe('helloWorld')
    expect(toCamelCase('user_name')).toBe('userName')
    expect(toCamelCase('page_size')).toBe('pageSize')
  })

  it('should not modify already camelCase strings', () => {
    expect(toCamelCase('helloWorld')).toBe('helloWorld')
  })
})

describe('toSnakeCase', () => {
  it('should convert camelCase to snake_case', () => {
    expect(toSnakeCase('helloWorld')).toBe('hello_world')
    expect(toSnakeCase('userName')).toBe('user_name')
    expect(toSnakeCase('pageSize')).toBe('page_size')
  })

  it('should not modify already snake_case strings', () => {
    expect(toSnakeCase('hello_world')).toBe('hello_world')
  })
})

describe('transformKeys', () => {
  it('should transform object keys recursively', () => {
    const input = { user_name: 'test', page_size: 10 }
    const result = transformKeys(input, toCamelCase)
    expect(result).toEqual({ userName: 'test', pageSize: 10 })
  })

  it('should handle nested objects', () => {
    const input = { user_info: { first_name: 'John', last_name: 'Doe' } }
    const result = transformKeys(input, toCamelCase)
    expect(result).toEqual({ userInfo: { firstName: 'John', lastName: 'Doe' } })
  })

  it('should handle arrays', () => {
    const input = { item_list: [{ item_name: 'a' }, { item_name: 'b' }] }
    const result = transformKeys(input, toCamelCase)
    expect(result).toEqual({ itemList: [{ itemName: 'a' }, { itemName: 'b' }] })
  })

  it('should preserve null and undefined', () => {
    expect(transformKeys(null, toCamelCase)).toBeNull()
    expect(transformKeys(undefined, toCamelCase)).toBeUndefined()
  })

  it('should preserve primitive values', () => {
    expect(transformKeys('hello', toCamelCase)).toBe('hello')
    expect(transformKeys(42, toCamelCase)).toBe(42)
    expect(transformKeys(true, toCamelCase)).toBe(true)
  })

  it('should not transform user-defined keys inside skip-list fields (env_vars / search_space / params)', () => {
    const input = {
      env_vars: { CUSTOM_VAR: 'x', other_key: 'y' },
      search_space: { learning_rate: { type: 'float', low: 1e-4 } },
      params: { learning_rate: 0.01, batch_size: 32, num_layers: 4 },
      normal_field: { sub_key: 1 },
    }
    const result = transformKeys(input, toCamelCase, SKIP_RECURSE_KEYS)
    expect(result).toEqual({
      envVars: { CUSTOM_VAR: 'x', other_key: 'y' },
      searchSpace: { learning_rate: { type: 'float', low: 1e-4 } },
      params: { learning_rate: 0.01, batch_size: 32, num_layers: 4 },
      normalField: { subKey: 1 },
    })
  })

  it('should skip-list keys symmetrically on the request (snake) transform', () => {
    const input = {
      searchSpace: { learning_rate: 0.01 },
      params: { batch_size: 32 },
    }
    const result = transformKeys(input, toSnakeCase, SKIP_RECURSE_KEYS)
    expect(result).toEqual({
      search_space: { learning_rate: 0.01 },
      params: { batch_size: 32 },
    })
  })
})
