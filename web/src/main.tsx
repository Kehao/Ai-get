import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import App from './App';
import '@/styles/global.less';

const container = document.getElementById('root');
if (container === null) {
  throw new Error('页面缺少 #root 挂载节点');
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
