import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
// The dashboard source is JavaScript while the Vite entry point is TypeScript.
// @ts-expect-error JavaScript component has no declaration file.
import App from './App.jsx';
import { jsx as _jsx } from "react/jsx-runtime";
createRoot(document.getElementById('root')!).render(/*#__PURE__*/_jsx(StrictMode, {
  children: /*#__PURE__*/_jsx(App, {})
}));
