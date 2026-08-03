import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useAuthStore } from '../stores/auth'

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})

describe('auth store — logout（issue #60 验收标准 1）', () => {
  it('logout 清除 localStorage agent.auth 并复位凭证与登录态', () => {
    const auth = useAuthStore()
    auth.setAuthenticated({ accessToken: 'access-t', refreshToken: 'refresh-t' }, 'A1001')

    expect(auth.isAuthenticated).toBe(true)
    expect(localStorage.getItem('agent.auth')).not.toBeNull()

    auth.logout()

    expect(auth.accessToken).toBe('')
    expect(auth.refreshToken).toBe('')
    expect(auth.employeeId).toBe('')
    expect(auth.isAuthenticated).toBe(false)
    expect(localStorage.getItem('agent.auth')).toBeNull()
  })
})
