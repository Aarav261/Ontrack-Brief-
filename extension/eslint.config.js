import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'

const unusedVars = [
  'warn',
  {
    args: 'none', // interceptor wrappers keep positional args for signature parity
    caughtErrors: 'none',
    varsIgnorePattern: '^[A-Z_]',
  },
]

export default [
  { ignores: ['dist', 'node_modules'] },

  // React popup source — runs in the browser, has access to the extension API
  {
    files: ['src/**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: { ...globals.browser, ...globals.webextensions },
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...js.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      'no-unused-vars': unusedVars,
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
    },
  },

  // Background service worker + content/injected scripts (plain JS, no bundler)
  {
    files: ['public/**/*.js'],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: 'script',
      globals: {
        ...globals.browser,
        ...globals.serviceworker,
        ...globals.webextensions,
        APP_URL: 'readonly', // injected via config.js (importScripts / manifest)
      },
    },
    rules: {
      ...js.configs.recommended.rules,
      'no-unused-vars': unusedVars,
    },
  },

  // Build/tooling config files run under Node
  {
    files: ['*.config.js'],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: 'module',
      globals: globals.node,
    },
    rules: {
      ...js.configs.recommended.rules,
      'no-unused-vars': unusedVars,
    },
  },
]
