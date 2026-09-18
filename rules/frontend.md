---
name: frontend
description: 前端开发规范。在编写、审查或重构前端代码时使用，覆盖目录结构、文件命名、HTML、CSS/SCSS、JavaScript、TypeScript、Vue、React、Git 提交、ESLint/Prettier、构建与性能、安全。由 AGENTS.md 引用。
---

# 前端开发规范

适用范围与触发条件见 `AGENTS.md` 的「语言与领域专属规则」：`.html`、`.css`、`.scss`、`.less`、`.js`、`.jsx`、`.ts`、`.tsx`、`.vue`、`.svelte`，以及前端构建与 ESLint/Prettier 配置均适用。

## 1. 项目目录规范

```text
src/
├── api/          # 接口请求
├── assets/       # 静态资源
├── components/   # 公共组件
├── composables/  # 组合式函数（Vue）
├── hooks/        # 业务 hooks（React）
├── constants/    # 常量
├── layouts/      # 布局
├── pages/        # 页面
├── router/       # 路由
├── store/        # 状态管理
├── styles/       # 全局样式
├── utils/        # 工具函数
└── App.vue / App.tsx
```

- 目录各司其职：不把页面级业务写进 `components/`，也不让 `components/` 反向依赖 `pages/`。
- 入口脚本 `main.ts` / `main.tsx` 与入口组件 `App.vue` / `App.tsx` 同层放置。
- 出现第二处相同逻辑时就抽到 `utils/` 或 `components/`，不要复制。

## 2. 命名规范

### 文件命名

- 组件：大驼峰，如 `UserList.vue`。
- 工具与页面：短横线，如 `user-info.ts`。
- 样式：短横线，如 `index.scss`、`button.scss`。

### 变量与函数

- 变量：小驼峰，如 `userList`。
- 常量：全大写下划线，如 `MAX_COUNT`。
- 布尔：`is` / `has` / `should` 开头，如 `isVisible`。
- 函数：动词开头，如 `getUserInfo()`。

## 3. HTML 规范

- 使用语义化标签：`header` / `main` / `section` / `aside` / `footer`。
- 类名使用短横线，如 `class="user-card"`。
- 禁止冗余标签，禁止行内样式。
- 图片必须加 `alt`，懒加载使用 `loading="lazy"`。

## 4. CSS / SCSS 规范

- 使用 BEM 或短横线命名。
- 嵌套不超过 3 层。
- 公共样式抽离到 `variables` / `mixins`。
- `z-index` 统一管理。
- 单位优先使用 `rem` / `vh` / `%`。
- 颜色使用变量，禁止硬编码。

```scss
// ✅ 变量 + BEM + 嵌套不超过 3 层
$color-primary: #1677ff;

.user-card {
  color: $color-primary;

  &__title {
    font-size: 1rem;
  }
}

// ❌ 嵌套过深，且颜色硬编码
.user-card {
  .title {
    .icon {
      color: #1677ff;
    }
  }
}
```

## 5. JavaScript 规范

- 使用 `const` / `let`，禁止 `var`。
- 优先使用箭头函数。
- 异步优先使用 `async` / `await`。
- 嵌套不超过 3 层。
- 禁止魔法数字，抽为常量。
- 数组操作优先使用 `map` / `filter` / `reduce`。

## 6. TypeScript 规范

- 必须定义接口或类型。
- 禁止 `any`，能用 `unknown` 替代。
- 接口与类型名称不加前缀或后缀：遵循 `AGENTS.md`「避免名称中的编码」，写 `User`、`OrderQuery`，而不是 `IUser`、`UserType`。
- 函数参数与返回值必须标注类型。
- 优先复用已有的 `type` / `interface`，不为同一结构重复定义。

## 7. Vue 规范

- 组件名使用多单词，避免与 HTML 标签重名。
- `props` 必须定义类型、默认值和校验。
- 指令使用缩写：`:`、`@`、`#`。
- 计算属性避免副作用。
- 慎用 `watch`，优先 `computed`。
- 方法命名遵循动词 + 名词。

## 8. React 规范

- 组件使用函数式 + Hooks。
- 状态扁平化，避免嵌套。
- 禁止在循环和条件中使用 Hooks。
- 事件处理函数以 `handle` 开头。
- 样式使用 CSS Modules 或 styled-components。

## 9. Git 提交规范

提交格式：`type(scope): content`

| type | 含义 |
| --- | --- |
| `feat` | 新功能 |
| `fix` | 修复 |
| `docs` | 文档 |
| `style` | 格式 |
| `refactor` | 重构 |
| `perf` | 性能 |
| `test` | 测试 |
| `chore` | 构建或工具 |

## 10. ESLint / Prettier 规范

- 2 空格缩进。
- 单引号。
- 语句末尾分号。
- 文件末尾空行。
- 禁止未使用变量。
- 禁止 `console`（生产环境）。

## 11. 构建与性能规范

- 图片压缩并转 WebP。
- 懒加载图片和组件。
- 路由懒加载。
- 高频事件做防抖节流。
- 大数据列表使用虚拟滚动。
- 减少冗余渲染。

## 12. 安全规范

- 防 XSS：过滤用户输入，不用 `innerHTML` / `v-html` 渲染不可信内容。
- 防 CSRF：token 校验。
- 敏感信息不放在 `localStorage`。
- 接口必须做权限控制。
- 禁止在前端明文存储密钥或 Token。

## 提交前检查

命令以项目 `package.json` 中的脚本名为准：

```bash
npm run lint        # ESLint 静态检查
npm run format      # Prettier 格式化
npx tsc --noEmit    # TypeScript 类型检查
npm run test        # 单元测试
npm run build       # 构建，确认无编译错误
```

## 快速检查清单

- [ ] 目录结构与文件命名符合第 1、2 节。
- [ ] 无行内样式，无硬编码颜色与魔法数字。
- [ ] 图片有 `alt` 且做了懒加载。
- [ ] TypeScript 无 `any`，参数与返回值已标注类型。
- [ ] 无未使用变量，生产代码无 `console`。
- [ ] 无 XSS 风险点（不渲染不可信 HTML）。
- [ ] 敏感信息未落在 `localStorage` 或前端明文。
- [ ] Git 提交信息符合 `type(scope): content`。
- [ ] 类型检查与构建均通过。
