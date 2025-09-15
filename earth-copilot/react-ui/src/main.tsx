// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import 'modern-normalize/modern-normalize.css';

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
