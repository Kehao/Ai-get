// 样式模块的类型声明：让 TS 认识 less 导入与 CSS Modules 的类名映射。

declare module '*.module.less' {
  const classes: { readonly [key: string]: string };
  export default classes;
}

declare module '*.less';
declare module '*.css';
declare module '*.svg' {
  const source: string;
  export default source;
}
declare module '*.png' {
  const source: string;
  export default source;
}
