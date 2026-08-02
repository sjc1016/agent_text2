import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'

import App from '../App.vue'

describe('App', () => {
  it('渲染根组件并含 Element Plus 按钮', () => {
    const wrapper = mount(App)
    expect(wrapper.find('[data-testid="app-root"]').exists()).toBe(true)
    expect(wrapper.find('.el-button').exists()).toBe(true)
  })
})
