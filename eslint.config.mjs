import pluginVue from 'eslint-plugin-vue'
import vueTsEslintConfig from '@vue/eslint-config-typescript'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'

/** Vue3 + TS monorepo 前端 lint 配置（flat config，eslint 10）。
 * 覆盖 frontend/{customer,agent,shared} 的 *.ts/*.vue；格式交给 prettier，
 * 经 skip-formatting 关闭 eslint 中与 prettier 冲突的格式规则。 */
export default [
  {
    name: 'app/files-to-lint',
    files: ['**/*.{ts,mts,tsx,vue}'],
  },
  {
    name: 'app/files-to-ignore',
    ignores: ['**/dist/**', '**/node_modules/**', '**/coverage/**', '**/.venv/**'],
  },
  ...pluginVue.configs['flat/essential'],
  ...vueTsEslintConfig(),
  {
    name: 'app/typescript-rules',
    files: ['**/*.{ts,mts,tsx,vue}'],
    rules: {
      // 下划线前缀参数 = 有意未使用（mock 签名保持真实契约，参数暂不消费）
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
  skipFormatting,
]
