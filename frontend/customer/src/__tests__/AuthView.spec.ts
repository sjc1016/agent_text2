import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { defineComponent } from 'vue'
import ElementPlus from 'element-plus'

import AuthView from '../views/AuthView.vue'
import { useSessionStore } from '../stores/session'

/** 占位视图：/chat 路由目标（认证成功/跳过后落点）。 */
const ChatStub = defineComponent({
  name: 'ChatStub',
  template: '<div data-testid="chat-stub">chat</div>',
})

function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/auth', component: AuthView },
      { path: '/chat', component: ChatStub },
    ],
  })
}

let pinia: Pinia

async function mountAuth() {
  pinia = createPinia()
  setActivePinia(pinia)
  const router = makeRouter()
  await router.push('/auth')
  await router.isReady()
  const wrapper = mount(AuthView, { global: { plugins: [router, pinia, ElementPlus] } })
  return { wrapper, router }
}

/** 填表：手机号 + 服务密码（默认均为有效值）。 */
async function fillForm(
  wrapper: Awaited<ReturnType<typeof mountAuth>>['wrapper'],
  phone = '13800001234',
) {
  await wrapper.find('[data-testid="phone-input"]').setValue(phone)
  await wrapper.find('[data-testid="password-input"]').setValue('svc12345')
}

const fetchMock = vi.fn()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('AuthView — default state（States 矩阵 default）', () => {
  it('渲染品牌/辅助文案/两输入框/认证主按钮/暂不认证文字按钮', async () => {
    const { wrapper } = await mountAuth()

    const card = wrapper.find('[data-testid="auth-card"]')
    expect(card.exists()).toBe(true)
    expect(card.text()).toContain('电信客服')
    expect(card.text()).toContain('请输入服务密码以查询和办理业务')

    const phone = wrapper.find('[data-testid="phone-input"]')
    expect(phone.exists()).toBe(true)
    expect(phone.attributes('placeholder')).toBe('请输入 11 位手机号')

    const password = wrapper.find('[data-testid="password-input"]')
    expect(password.exists()).toBe(true)
    expect(password.attributes('type')).toBe('password')
    expect(password.attributes('placeholder')).toBe('请输入服务密码')

    const submit = wrapper.find('[data-testid="auth-submit"]')
    expect(submit.text()).toContain('认证')
    expect(wrapper.find('[data-testid="auth-skip"]').text()).toContain('暂不认证，先咨询')
  })

  it('手机号未填时主按钮禁用；填满 11 位后启用（States 矩阵 disabled）', async () => {
    const { wrapper } = await mountAuth()
    const submit = wrapper.find('[data-testid="auth-submit"]')
    expect((submit.element as HTMLButtonElement).disabled).toBe(true)

    await fillForm(wrapper, '138')
    expect(
      (wrapper.find('[data-testid="auth-submit"]').element as HTMLButtonElement).disabled,
    ).toBe(true)

    await fillForm(wrapper, '13800001234')
    expect(
      (wrapper.find('[data-testid="auth-submit"]').element as HTMLButtonElement).disabled,
    ).toBe(false)
  })

  it('手机号聚焦添加 shadow-focus 外发光环类，失焦移除', async () => {
    const { wrapper } = await mountAuth()
    const phone = wrapper.find('[data-testid="phone-input"]')
    expect(phone.classes()).not.toContain('text-input--focus')

    await phone.trigger('focus')
    expect(phone.classes()).toContain('text-input--focus')

    await phone.trigger('blur')
    expect(phone.classes()).not.toContain('text-input--focus')
  })

  it('服务密码眼睛图标切换明文（type password ↔ text）', async () => {
    const { wrapper } = await mountAuth()
    const password = wrapper.find('[data-testid="password-input"]')
    const toggle = wrapper.find('[data-testid="password-toggle"]')

    expect(password.attributes('type')).toBe('password')
    await toggle.trigger('click')
    expect(password.attributes('type')).toBe('text')
    expect(toggle.attributes('aria-label')).toBe('隐藏服务密码')

    await toggle.trigger('click')
    expect(password.attributes('type')).toBe('password')
    expect(toggle.attributes('aria-label')).toBe('显示服务密码')
  })
})

describe('AuthView — login 成功升格客户（US-2）', () => {
  it('调用 POST /api/auth/login，成功写入凭证 + 脱敏号码 + 跳转 /chat', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        access_token: 'access-t',
        refresh_token: 'refresh-t',
        token_type: 'bearer',
      }),
    })
    const { wrapper, router } = await mountAuth()
    await fillForm(wrapper)
    await wrapper.find('[data-testid="auth-form"]').trigger('submit')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/auth/login')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({
      phone: '13800001234',
      service_password: 'svc12345',
    })

    const session = useSessionStore()
    expect(session.conversationState).toBe('authenticated')
    expect(session.maskedPhone).toBe('138****1234')
    expect(session.accessToken).toBe('access-t')
    expect(session.refreshToken).toBe('refresh-t')
    expect(router.currentRoute.value.path).toBe('/chat')

    // 持久化：刷新可恢复已认证会话（会话 store 状态来源注释）
    const persisted = JSON.parse(localStorage.getItem('customer.auth') ?? '{}')
    expect(persisted.accessToken).toBe('access-t')
    expect(persisted.maskedPhone).toBe('138****1234')
  })
})

describe('AuthView — error state（States 矩阵 error）', () => {
  it('认证失败：两输入框错误态环 + 错误文案「手机号或服务密码错误」', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      json: async () => ({ detail: '手机号或服务密码错误' }),
    })
    const { wrapper } = await mountAuth()
    await fillForm(wrapper)
    await wrapper.find('[data-testid="auth-form"]').trigger('submit')
    await flushPromises()

    const error = wrapper.find('[data-testid="auth-error"]')
    expect(error.exists()).toBe(true)
    expect(error.text()).toBe('手机号或服务密码错误')

    const phone = wrapper.find('[data-testid="phone-input"]')
    const password = wrapper.find('[data-testid="password-input"]')
    expect(phone.classes()).toContain('text-input--error')
    expect(password.classes()).toContain('text-input--error')

    // 失败不升格：仍访客，留在 auth 页
    const session = useSessionStore()
    expect(session.conversationState).toBe('unauthenticated')
  })
})

describe('AuthView — loading state（States 矩阵 loading）', () => {
  it('提交中主按钮禁用 + 白 spinner + 文字「认证中…」', async () => {
    let resolveFetch!: (value: unknown) => void
    fetchMock.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve
      }),
    )
    const { wrapper } = await mountAuth()
    await fillForm(wrapper)
    await wrapper.find('[data-testid="auth-form"]').trigger('submit')

    const submit = wrapper.find('[data-testid="auth-submit"]')
    expect((submit.element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.find('[data-testid="auth-submit-spinner"]').exists()).toBe(true)
    expect(submit.text()).toContain('认证中…')

    resolveFetch({
      ok: true,
      json: async () => ({ access_token: 'at', refresh_token: 'rt', token_type: 'bearer' }),
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="auth-submit-spinner"]').exists()).toBe(false)
  })
})

describe('AuthView — 暂不认证，先咨询（US-2 第二路径）', () => {
  it('点击返回 /chat，保持访客身份', async () => {
    const { wrapper, router } = await mountAuth()
    await wrapper.find('[data-testid="auth-skip"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/chat')
    const session = useSessionStore()
    expect(session.conversationState).toBe('unauthenticated')
    expect(session.maskedPhone).toBe('')
    expect(session.accessToken).toBe('')
  })
})
