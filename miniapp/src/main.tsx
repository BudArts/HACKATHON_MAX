import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './App';
import './styles/global.css';

const container = document.getElementById('root');
if (!container) throw new Error('Корневой элемент не найден');

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
