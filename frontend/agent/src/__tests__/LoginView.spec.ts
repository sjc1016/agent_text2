import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { defineComponent } from 'vue'
import ElementPlus from 'element-plus'

import LoginView from '../views/LoginView.vue'
import { useAuthStore } from '../stores/auth'

/** 占位视图：/queue 路由目标（登录成功落点 = 工作台待接入页）。 */
const QueueStub = defineComponent({
  name: 'QueueStub',
  template: '<div data-testid="queue-stub">queue</div>',
})

function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', component: LoginView },
      { path: '/queue', component: QueueStub },
    ],
  })
}

let pinia: Pinia

async function mountLogin() {
  pinia = createPinia()
  setActivePinia(pinia)
  const router = makeRouter()
  await router.push('/login')
  await router.isReady()
  const wrapper = mount(LoginView, { global: { plugins: [router, pinia, ElementPlus] } })
  return { wrapper, router }
}

/** 填表：工号 + 密码（默认均为有效值）。 */
async function fillForm(
  wrapper: Awaited<ReturnType<typeof mountLogin>>['wrapper'],
  employeeId = '1001',
  password = 'agent123',
) {
  await wrapper.find('[data-testid="employee-id-input"]').setValue(employeeId)
  await wrapper.find('[data-testid="password-input"]').setValue(password)
}

const fetchMock = vi.fn()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('LoginView — default state（States 矩阵 default）', () => {
  it('渲染品牌标识/工号输入/密码输入(明文切换)/登录主按钮', async () => {
    const { wrapper } = await mountLogin()

    const card = wrapper.find('[data-testid="login-card"]')
    expect(card.exists()).toBe(true)
    expect(card.text()).toContain('客服工作台')

    const employeeId = wrapper.find('[data-testid="employee-id-input"]')
    expect(employeeId.exists()).toBe(true)
    expect(employeeId.attributes('placeholder')).toBe('请输入工号')
    expect(card.text()).toContain('工号')

    const password = wrapper.find('[data-testid="password-input"]')
    expect(password.exists()).toBe(true)
    expect(password.attributes('type')).toBe('password')
    expect(password.attributes('placeholder')).toBe('请输入密码')

    const submit = wrapper.find('[data-testid="login-submit"]')
    expect(submit.text()).toContain('登录')
  })

  it('工号输入聚焦添加 shadow-focus 外发光环类，失焦移除', async () => {
    const { wrapper } = await mountLogin()
    const employeeId = wrapper.find('[data-testid="employee-id-input"]')
    expect(employeeId.classes()).not.toContain('text-input--focus')

    await employeeId.trigger('focus')
    expect(employeeId.classes()).toContain('text-input--focus')

    await employeeId.trigger('blur')
    expect(employeeId.classes()).not.toContain('text-input--focus')
  })

  it('密码眼睛图标切换明文（type password ↔ text）', async () => {
    const { wrapper } = await mountLogin()
    const password = wrapper.find('[data-testid="password-input"]')
    const toggle = wrapper.find('[data-testid="password-toggle"]')

    expect(password.attributes('type')).toBe('password')
    await toggle.trigger('click')
    expect(password.attributes('type')).toBe('text')
    expect(toggle.attributes('aria-label')).toBe('隐藏密码')

    await toggle.trigger('click')
    expect(password.attributes('type')).toBe('password')
    expect(toggle.attributes('aria-label')).toBe('显示密码')
  })

  it('工号或密码为空时主按钮禁用，两者均填后启用（States 矩阵 disabled）', async () => {
    const { wrapper } = await mountLogin()
    const submit = wrapper.find('[data-testid="login-submit"]')
    expect((submit.element as HTMLButtonElement).disabled).toBe(true)

    // 仅填工号：仍禁用
    await fillForm(wrapper, '1001', '')
    expect(
      (wrapper.find('[data-testid="login-submit"]').element as HTMLButtonElement).disabled,
    ).toBe(true)

    // 仅填密码：仍禁用
    await fillForm(wrapper, '', 'agent123')
    expect(
      (wrapper.find('[data-testid="login-submit"]').element as HTMLButtonElement).disabled,
    ).toBe(true)

    // 两者均填：启用
    await fillForm(wrapper, '1001', 'agent123')
    expect(
      (wrapper.find('[data-testid="login-submit"]').element as HTMLButtonElement).disabled,
    ).toBe(false)
  })
})

describe('LoginView — 登录成功进入工作台（US-19）', () => {
  it('调用 POST /api/agents/login，成功写入凭证 + 跳转 /queue', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        access_token: 'access-t',
        refresh_token: 'refresh-t',
        token_type: 'bearer',
      }),
    })
    const { wrapper, router } = await mountLogin()
    await fillForm(wrapper, '1001', 'agent123')
    await wrapper.find('[data-testid="login-form"]').trigger('submit')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/agents/login')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({
      employee_id: '1001',
      password: 'agent123',
    })

    const auth = useAuthStore()
    expect(auth.accessToken).toBe('access-t')
    expect(auth.refreshToken).toBe('refresh-t')
    expect(auth.employeeId).toBe('1001')
    expect(router.currentRoute.value.path).toBe('/queue')

    // 持久化：刷新可恢复已登录会话（后续坐席 WS/REST 鉴权依赖凭证）
    const persisted = JSON.parse(localStorage.getItem('agent.auth') ?? '{}')
    expect(persisted.accessToken).toBe('access-t')
    expect(persisted.employeeId).toBe('1001')
  })
})

describe('LoginView — error state（States 矩阵 error）', () => {
  it('登录失败：两输入框错误态环 + 错误文案「工号或密码错误」', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      json: async () => ({ detail: '工号或密码错误' }),
    })
    const { wrapper } = await mountLogin()
    await fillForm(wrapper, '1001', 'agent123')
    await wrapper.find('[data-testid="login-form"]').trigger('submit')
    await flushPromises()

    const error = wrapper.find('[data-testid="login-error"]')
    expect(error.exists()).toBe(true)
    expect(error.text()).toBe('工号或密码错误')

    const employeeId = wrapper.find('[data-testid="employee-id-input"]')
    const password = wrapper.find('[data-testid="password-input"]')
    expect(employeeId.classes()).toContain('text-input--error')
    expect(password.classes()).toContain('text-input--error')

    // 失败不登录：无凭证，留在 login 页
    const auth = useAuthStore()
    expect(auth.isAuthenticated).toBe(false)
  })
})

describe('LoginView — loading state（States 矩阵 loading）', () => {
  it('提交中主按钮禁用 + 白 spinner + 文字「登录中…」', async () => {
    let resolveFetch!: (value: unknown) => void
    fetchMock.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve
      }),
    )
    const { wrapper } = await mountLogin()
    await fillForm(wrapper, '1001', 'agent123')
    await wrapper.find('[data-testid="login-form"]').trigger('submit')

    const submit = wrapper.find('[data-testid="login-submit"]')
    expect((submit.element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.find('[data-testid="login-submit-spinner"]').exists()).toBe(true)
    expect(submit.text()).toContain('登录中…')

    resolveFetch({
      ok: true,
      json: async () => ({ access_token: 'at', refresh_token: 'rt', token_type: 'bearer' }),
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="login-submit-spinner"]').exists()).toBe(false)
  })
})
