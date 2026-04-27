import type { Rule } from 'antd/es/form'

export const emailRule: Rule = {
  type: 'email',
  message: '请输入有效的邮箱地址',
}

export const requiredRule = (message = '此字段为必填项'): Rule => ({
  required: true,
  message,
})

export const passwordRule: Rule = {
  min: 8,
  message: '密码至少 8 个字符',
}

export const usernameRule: Rule = {
  min: 3,
  max: 32,
  message: '用户名长度为 3-32 个字符',
  pattern: /^[a-zA-Z0-9_-]+$/,
}
