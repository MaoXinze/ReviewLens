module.exports = {
  root: true,
  env: { browser: true, es2021: true, node: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
  },
  plugins: ['@typescript-eslint', 'react-hooks'],
  ignorePatterns: ['dist', 'node_modules', '*.config.ts'],
  rules: {
    // 未使用变量：允许下划线前缀参数（接口占位）
    '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    // 显式 any 容忍（渐进式引入，避免大面积重构）
    '@typescript-eslint/no-explicit-any': 'off',
    // React 18 自动 JSX runtime，无需引入 React
    'react/react-in-jsx-scope': 'off',
    // 测试/工具文件允许 console
    'no-console': 'off',
  },
};
