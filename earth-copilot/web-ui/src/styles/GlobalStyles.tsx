// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

export const GlobalStyles = () => (
  <style>{`
    :root {
      --bg: #ffffff;
      --panel: #ffffff;
      --muted: #6b7280;
      --text: #0f172a;
      --brand: #0ea5e9;
      --border: #e5e7eb;
      --side: 420px;
      --side-left: var(--side);
      --chat-panel-width: 420px;
    }

    html, body {
      height: 100%;
      margin: 0;
      background: #ffffff;
      color: var(--text);
      font-family: "Segoe UI", "Segoe UI Variable Text", -apple-system, BlinkMacSystemFont, system-ui, Roboto, Inter, "Helvetica Neue", Arial, "Noto Sans";
    }

    #root {
      height: 100vh;
      overflow: hidden;
    }

    * {
      box-sizing: border-box;
    }

    .app-container {
      height: 100vh;
      display: flex;
      flex-direction: column;
    }

    .top-header {
      height: 64px;
      display: grid;
      grid-template-columns: 1fr auto;
      align-items: center;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
      padding: 0 20px;
      position: relative;
    }

    /* Position Microsoft logo on the left side, moved further left */
    .top-header > div:first-child {
      position: absolute;
      left: 8px;
      top: 50%;
      transform: translateY(-50%);
      z-index: 10;
    }

    .app {
      display: grid;
      grid-template-columns: var(--side-left) 1fr var(--chat-panel-width);
      gap: 0;
      height: calc(100vh - 64px);
    }

    .center {
      position: relative;
      background: #0a0f16;
      min-height: calc(100vh - 64px);
    }

    /* Resizable Panel Styles */
    .resizable-panel {
      position: relative;
      background: var(--panel);
      border-left: 1px solid var(--border);
      overflow: hidden;
    }

    .chat-panel {
      display: flex;
      flex-direction: column;
      height: 100%;
    }

    .resize-handle:hover {
      background-color: rgba(0, 122, 204, 0.1) !important;
    }

    .map {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
    }

    .landing-container {
      height: calc(100vh - 64px);
      display: flex;
      align-items: center;
      justify-content: center;
      background: #ffffff;
      position: relative;
    }

    .landing-container::before {
      display: none;
    }

    .landing-content {
      position: relative;
      z-index: 3;
      width: 100%;
      height: 100%;
      padding: 2rem;
      display: flex;
      flex-direction: column;
    }

    .landing-top-left {
      position: absolute;
      top: 2rem;
      left: 2rem;
    }

    .landing-top-right {
      position: absolute;
      top: 0.5rem;
      right: 0.5rem;
      z-index: 100;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .landing-top-left .landing-title {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 0;
      background: none;
      border: none;
      backdrop-filter: none;
      box-shadow: none;
      max-width: none;
      margin: 0;
    }

    .landing-top-left .landing-title span {
      font-size: 28px;
      font-weight: 500;
      color: #333333;
      text-shadow: none;
      letter-spacing: 0.5px;
    }

    .landing-top {
      margin-bottom: 60px;
    }

    .landing-center {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      margin-bottom: 40px;
    }

    .landing-prompt-box {
      text-align: center;
      margin-bottom: 24px;
      padding: 8px 16px;
      background: none;
      border: none;
      border-radius: 0;
      box-shadow: none;
      max-width: 600px;
      margin-left: auto;
      margin-right: auto;
      backdrop-filter: none;
    }

    .landing-prompt {
      font-size: 11px;
      font-weight: 400;
      margin: 0;
      color: #999999;
      text-shadow: none;
      letter-spacing: 0.3px;
      opacity: 0.8;
    }    .landing-buttons {
      display: flex;
      gap: 1rem;
      justify-content: center;
      flex-wrap: wrap;
    }

    .search-form {
      width: 100%;
      max-width: 600px;
      margin: 0 auto;
    }

    .search-input-container {
      display: flex;
      gap: 12px;
      background: rgba(255, 255, 255, 0.08);
      backdrop-filter: blur(20px);
      border: 2px solid rgba(255, 255, 255, 0.15);
      border-radius: 16px;
      padding: 16px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
      max-width: 800px;
      width: 100%;
      margin: 0 auto;
    }

    .search-input {
      flex: 1;
      background: rgba(255, 255, 255, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.3);
      border-radius: 8px;
      padding: 12px 16px;
      font-size: 18px;
      color: #333333;
      outline: none;
      transition: all 0.3s ease;
    }

    .search-input:focus {
      background: rgba(255, 255, 255, 0.95);
      border-color: #1e3a8a;
      box-shadow: 0 0 0 3px rgba(30, 58, 138, 0.1);
    }

    .search-input::placeholder {
      color: #666666;
    }

    .search-button {
      background: #94a3b8;
      border: 2px solid #94a3b8;
      color: #ffffff;
      padding: 12px 24px;
      border-radius: 8px;
      font-size: 18px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.3s ease;
      white-space: nowrap;
    }

    .search-button:hover {
      background: #64748b;
      border-color: #64748b;
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(148, 163, 184, 0.3);
    }

    .landing {
      position: relative;
      height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      background-image: url('https://images.unsplash.com/photo-1446776653964-20c1d3a81b06?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=2070&q=80');
      background-size: cover;
      background-position: center;
      background-repeat: no-repeat;
    }

    .landing::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(255, 255, 255, 0.7);
      z-index: 1;
    }

        .landing-page {
      min-height: 100vh;
      background: #ffffff;
      display: flex;
      flex-direction: column;
      color: #333333;
      position: relative;
    }

    .landing-top {
      margin-bottom: 60px;
    }

    .landing-center {
      margin-bottom: 40px;
    }

    .landing-prompt-box {
      margin-bottom: 40px;
      border: 2px solid rgba(255, 255, 255, 0.3);
      border-radius: 16px;
      padding: 24px 32px;
      background: rgba(255, 255, 255, 0.05);
      backdrop-filter: blur(10px);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }

    .landing-prompt {
      font-size: 1.8rem;
      color: var(--text);
      font-weight: 600;
      text-align: center;
      margin: 0;
    }

    .btn.white {
      background: #1e3a8a;
      border: 2px solid #1e3a8a;
      color: #ffffff;
      padding: 16px 32px;
      border-radius: 8px;
      font-size: 16px;
      font-weight: 600;
      min-width: 180px;
      transition: all 0.3s ease;
      text-shadow: none;
      box-shadow: 0 2px 8px rgba(30, 58, 138, 0.2);
    }

    .btn.white:hover {
      background: #64748b;
      border-color: #64748b;
      color: #ffffff;
      transform: translateY(-2px);
      box-shadow: 0 4px 16px rgba(100, 116, 139, 0.3);
    }

    /* Dataset Detail Panel Styles */
    .dataset-detail-panel {
      position: fixed;
      top: 0;
      right: 0;
      width: 400px;
      height: 100vh;
      background: white;
      border-left: 1px solid #e9ecef;
      box-shadow: -2px 0 10px rgba(0, 0, 0, 0.1);
      z-index: 1000;
      overflow-y: auto;
    }

    .detail-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 20px;
      border-bottom: 1px solid #e9ecef;
      background: #f8f9fa;
    }

    .detail-header h2 {
      margin: 0;
      font-size: 18px;
      font-weight: 600;
      color: #333;
    }

    .close-btn {
      background: none;
      border: none;
      font-size: 24px;
      cursor: pointer;
      color: #666;
      padding: 0;
      width: 30px;
      height: 30px;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 4px;
    }

    .close-btn:hover {
      background: #e9ecef;
      color: #333;
    }

    .detail-content {
      padding: 20px;
    }

    .detail-section {
      margin-bottom: 24px;
    }

    .detail-section h3 {
      font-size: 16px;
      font-weight: 600;
      margin: 0 0 12px 0;
      color: #333;
    }

    .detail-section p {
      margin: 0 0 12px 0;
      line-height: 1.5;
      color: #666;
    }

    .spec-grid {
      display: grid;
      gap: 8px;
    }

    .spec-item {
      display: flex;
      justify-content: space-between;
      padding: 8px 0;
      border-bottom: 1px solid #f0f0f0;
      font-size: 14px;
    }

    .spec-item strong {
      color: #333;
      margin-right: 8px;
    }

    .applications-list {
      margin: 0;
      padding-left: 20px;
    }

    .applications-list li {
      margin-bottom: 4px;
      color: #666;
      font-size: 14px;
    }

    .doc-link {
      color: #0078d4;
      text-decoration: none;
      font-weight: 500;
    }

    .doc-link:hover {
      text-decoration: underline;
    }

    .access-buttons {
      display: flex;
      gap: 12px;
      margin-top: 16px;
    }

    .btn.primary {
      background: #0078d4;
      color: white;
      border: 1px solid #0078d4;
      padding: 8px 16px;
      border-radius: 4px;
      font-size: 14px;
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .btn.primary:hover {
      background: #106ebe;
      border-color: #106ebe;
    }

    .btn.secondary {
      background: white;
      color: #0078d4;
      border: 1px solid #0078d4;
      padding: 8px 16px;
      border-radius: 4px;
      font-size: 14px;
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .btn.secondary:hover {
      background: #f0f8ff;
    }

    /* Dropdown Styles */
    .dataset-dropdown {
      position: relative;
      width: 100%;
      margin-bottom: 16px;
    }

    .dropdown-button {
      width: 100%;
      padding: 12px 16px;
      background: #f8f9fa;
      border: 1px solid #e9ecef;
      border-radius: 6px;
      font-size: 14px;
      font-weight: 500;
      color: #333;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      transition: all 0.2s ease;
    }

    .dropdown-button:hover {
      background: #e9ecef;
      border-color: #0078d4;
    }

    .dropdown-button.open {
      border-color: #0078d4;
      border-bottom-left-radius: 0;
      border-bottom-right-radius: 0;
    }

    .dropdown-arrow {
      font-size: 12px;
      transition: transform 0.2s ease;
      color: #666;
    }

    .dropdown-arrow.open {
      transform: rotate(180deg);
    }

    .dropdown-menu {
      position: absolute;
      top: 100%;
      left: 0;
      right: 0;
      background: white;
      border: 1px solid #0078d4;
      border-top: none;
      border-radius: 0 0 6px 6px;
      max-height: 300px;
      overflow-y: auto;
      z-index: 1000;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }

    .dropdown-item {
      padding: 10px 16px;
      cursor: pointer;
      font-size: 14px;
      color: #333;
      border-bottom: 1px solid #f0f0f0;
      transition: background-color 0.2s ease;
    }

    .dropdown-item:hover {
      background: #f8f9fa;
    }

    .dropdown-item:last-child {
      border-bottom: none;
    }

    .dropdown-item.selected {
      background: #e3f2fd;
      color: #0078d4;
      font-weight: 500;
    }

    /* Dataset Description Styles */
    .dataset-description-panel {
      margin-top: 16px;
      padding: 16px;
      background: #f8f9fa;
      border: 1px solid #e9ecef;
      border-radius: 8px;
    }

    .dataset-description-panel h3 {
      margin: 0 0 12px 0;
      font-size: 16px;
      font-weight: 600;
      color: #333;
    }

    .dataset-description-panel p {
      margin: 0 0 12px 0;
      font-size: 14px;
      line-height: 1.5;
      color: #666;
    }

    .dataset-metadata {
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }

    .metadata-item {
      display: flex;
      justify-content: space-between;
      font-size: 13px;
      padding: 4px 0;
    }

    .metadata-label {
      font-weight: 500;
      color: #333;
    }

    .metadata-value {
      color: #666;
      text-align: right;
    }

    .btn {
      padding: 10px 16px;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: transparent;
      color: var(--text);
      cursor: pointer;
      font: inherit;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 44px;
      transition: all 0.2s ease;
    }

    .btn:hover {
      background: rgba(255, 255, 255, 0.05);
      transform: translateY(-1px);
    }

    .btn.primary {
      background: #0ea5e9;
      color: #fff;
      border-color: #0284c7;
    }

    .btn.primary:hover {
      background: #0284c7;
      transform: translateY(-1px);
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.3s ease;
      cursor: pointer;
      padding: 6px 4px;
      border-radius: 6px;
      position: relative;
    }

    .brand:hover {
      background: rgba(255, 255, 255, 0.08);
      transform: translateY(-1px);
    }

    .brand svg {
      color: var(--brand);
      transition: all 0.3s ease;
    }

    .brand:hover svg {
      color: #3b82f6;
      transform: scale(1.1);
    }

    .brand-name {
      font-weight: 500;
      letter-spacing: 0.3px;
      color: #333333;
      font-size: 28px;
      transition: color 0.3s ease;
      white-space: nowrap;
      font-family: "Segoe UI", "Segoe UI Variable Text", -apple-system, BlinkMacSystemFont, system-ui, Roboto, Inter, "Helvetica Neue", Arial, "Noto Sans";
    }

    .brand:hover .brand-name {
      color: #333333;
    }

    .left {
      border-right: 1px solid var(--border);
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      background: var(--panel);
      overflow-y: auto;
      position: relative;
      transition: all 0.3s ease;
    }

    .left.collapsed {
      padding: 0;
      border-right: none;
      width: 40px;
      min-width: 40px;
    }

    .collapse-arrow {
      position: absolute;
      top: 50%;
      right: 4px;
      transform: translateY(-50%);
      width: 32px;
      height: 32px;
      background: rgba(255, 255, 255, 0.9);
      border: none;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.3s ease;
      z-index: 1000;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
      backdrop-filter: blur(4px);
    }

    .collapse-arrow:hover {
      transform: translateY(-50%) scale(1.1);
      background: rgba(255, 255, 255, 0.95);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    }

    .collapse-arrow svg {
      color: #0078d4;
      transition: all 0.3s ease;
      width: 20px;
      height: 20px;
    }

    .left.collapsed .collapse-arrow {
      right: 4px;
    }

    .left.collapsed .collapse-arrow svg {
      transform: rotate(180deg);
      color: #0078d4;
    }

    .right {
      display: flex;
      flex-direction: column;
      height: calc(100vh - 64px);
      overflow: hidden;
    }

    .title {
      font-weight: 500;
      letter-spacing: 0.2px;
      color: var(--muted);
    }

    .data-catalog-title {
      font-size: 16px;
      font-weight: 500;
      letter-spacing: 0.3px;
      color: #333333;
      font-family: "Segoe UI", "Segoe UI Variable Text", -apple-system, BlinkMacSystemFont, system-ui, Roboto, Inter, "Helvetica Neue", Arial, "Noto Sans";
    }

    .data-section {
      border: 1px solid #d1d5db;
      border-radius: 8px;
      padding: 12px;
      margin-bottom: 16px;
      background: #ffffff;
    }

    .data-section-title {
      font-size: 14px;
      font-weight: 600;
      color: #1f2937;
      margin-bottom: 8px;
      letter-spacing: 0.5px;
    }

    .data-section.private {
      border-color: #d1d5db;
      background: #ffffff;
    }

    .data-section.public {
      border-color: #d1d5db;
      background: #ffffff;
    }

    .select {
      width: 100%;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: transparent;
      color: var(--text);
    }

    .desc {
      font-size: 13px;
      color: var(--muted);
      line-height: 1.35;
      overflow-wrap: anywhere;
    }

    .desc-scroll {
      max-height: 160px;
      overflow: auto;
      padding-right: 6px;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
      background: transparent;
    }

    /* Modern Chat UI Overhaul */
    .chat {
      display: flex;
      flex-direction: column;
      height: 100%;
      background: #ffffff;
      border-radius: 12px;
      box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
      overflow: hidden;
    }

    .header {
      padding: 20px 24px;
      background: linear-gradient(135deg, #60A5FA 0%, #3B82F6 100%);
      color: white;
      font-weight: 600;
      font-size: 18px;
      display: flex;
      align-items: center;
      justify-content: center;
      border-bottom: none;
      box-shadow: 0 2px 8px rgba(59, 130, 246, 0.15);
    }

    /* Remove earth icon from header */

    .messages {
      flex: 1;
      overflow-y: auto;
      overflow-x: hidden;
      padding: 24px;
      background: linear-gradient(180deg, #ffffff 0%, #f8fafc 50%, #f1f5f9 100%);
      display: flex;
      flex-direction: column;
      gap: 20px;
      scroll-behavior: smooth;
      scrollbar-gutter: stable;
    }

    /* Enhanced scrollbar styling */
    .messages::-webkit-scrollbar {
      width: 12px;
    }

    .messages::-webkit-scrollbar-track {
      background: rgba(241, 245, 249, 0.3);
      border-radius: 6px;
      margin: 8px 0;
    }

    .messages::-webkit-scrollbar-thumb {
      background: rgba(148, 163, 184, 0.4);
      border-radius: 6px;
      border: 2px solid transparent;
      background-clip: content-box;
      transition: background 0.2s ease;
    }

    .messages::-webkit-scrollbar-thumb:hover {
      background: rgba(148, 163, 184, 0.7);
      background-clip: content-box;
    }

    .messages::-webkit-scrollbar-thumb:active {
      background: rgba(148, 163, 184, 0.9);
      background-clip: content-box;
    }

    /* Message Bubbles */
    .row {
      display: flex;
      width: 100%;
      margin-bottom: 4px;
      align-items: flex-end;
      gap: 12px;
    }

    .row.user {
      justify-content: flex-end;
    }

    .row.assistant {
      justify-content: flex-start;
    }

    .message-wrapper {
      display: flex;
      flex-direction: column;
      max-width: 75%;
      position: relative;
    }

    .row.user .message-wrapper {
      align-items: flex-end;
    }

    .row.assistant .message-wrapper {
      align-items: flex-start;
    }

    .msg {
      padding: 16px 20px;
      border-radius: 20px;
      word-wrap: break-word;
      line-height: 1.5;
      font-size: 14px;
      position: relative;
      box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
      backdrop-filter: blur(10px);
      display: inline-block;
      max-width: 100%;
      white-space: pre-wrap;
      word-break: break-word;
    }

    .user .msg {
      background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 50%, #dee2e6 100%);
      color: #000000;
      border-bottom-right-radius: 6px;
      position: relative;
    }

    .user .msg::after {
      content: '';
      position: absolute;
      bottom: 0;
      right: -8px;
      width: 0;
      height: 0;
      border: 8px solid transparent;
      border-bottom-color: #dee2e6;
      border-right: none;
      border-bottom-right-radius: 4px;
    }

    .assistant .msg {
      background: rgba(255, 255, 255, 0.95);
      color: #2d3748;
      border: 1px solid rgba(226, 232, 240, 0.8);
      border-bottom-left-radius: 6px;
      position: relative;
    }

    .assistant .msg::after {
      content: '';
      position: absolute;
      bottom: 0;
      left: -8px;
      width: 0;
      height: 0;
      border: 8px solid transparent;
      border-bottom-color: rgba(255, 255, 255, 0.95);
      border-left: none;
      border-bottom-left-radius: 4px;
    }

    .assistant .msg a {
      color: #667eea;
      text-decoration: none;
      font-weight: 500;
    }

    .assistant .msg a:hover {
      text-decoration: underline;
    }

    /* Avatar styling - REMOVED per user request */

    /* Loading indicator */
    .loading-indicator {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 16px 20px;
      color: #718096;
      font-style: normal;
      background: rgba(255, 255, 255, 0.95);
      border-radius: 20px;
      border-bottom-left-radius: 6px;
      box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(226, 232, 240, 0.8);
      min-width: 200px;
    }

    .loading-indicator span:first-child {
      animation: pulse 1.5s ease-in-out infinite;
      font-size: 16px;
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }

    .loading-indicator span:last-child {
      font-weight: 500;
    }

    /* Reactions */
    .reactions {
      display: flex;
      gap: 8px;
      margin-top: 8px;
      align-items: center;
      opacity: 0;
      transition: opacity 0.2s ease;
    }

    .row:hover .reactions {
      opacity: 1;
    }

    .icon-btn {
      background: rgba(255, 255, 255, 0.9);
      border: 1px solid rgba(226, 232, 240, 0.8);
      padding: 6px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #718096;
      transition: all 0.2s ease;
      cursor: pointer;
    }

    .icon-btn:hover {
      background: #f7fafc;
      color: #4a5568;
      transform: translateY(-1px);
    }

    /* Modern Footer */
    .footer {
      padding: 20px 24px;
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(20px);
      border-top: 1px solid rgba(226, 232, 240, 0.6);
      box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.06);
    }

    .footer-content {
      display: flex;
      gap: 5px;
      align-items: flex-end;
      width: 100%;
      position: relative;
    }

    textarea {
      flex: 1;
      min-width: 0;
      min-height: 52px;
      max-height: 120px;
      padding: 16px 20px;
      border: 2px solid #e2e8f0;
      border-radius: 26px;
      background: rgba(255, 255, 255, 0.9);
      color: #2d3748;
      resize: none;
      font-size: 14px;
      line-height: 1.5;
      font-family: inherit;
      outline: none;
      transition: all 0.3s ease;
      box-sizing: border-box;
      backdrop-filter: blur(10px);
    }

    textarea:focus {
      border-color: #87CEEB;
      box-shadow: 0 0 0 3px rgba(135, 206, 235, 0.1);
      background: rgba(255, 255, 255, 1);
    }

    textarea::placeholder {
      color: #a0aec0;
      font-weight: 400;
    }

    .btn.send {
      padding: 12px 20px;
      border-radius: 26px;
      background: linear-gradient(135deg, #a0aec0 0%, #9ca3af 100%);
      color: white;
      border: 2px solid transparent;
      cursor: pointer;
      font-weight: 600;
      font-size: 14px;
      min-width: 80px;
      height: 52px;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.3s ease;
      box-shadow: 0 2px 8px rgba(160, 174, 192, 0.2);
      backdrop-filter: blur(10px);
      align-self: flex-end;
    }

    /* When input has text, change to blue with glowing effect */
    .btn.send.has-text:not(:disabled) {
      background: linear-gradient(135deg, #60A5FA 0%, #3B82F6 100%);
      border: 2px solid #3B82F6;
      box-shadow: 0 0 20px rgba(59, 130, 246, 0.6), 0 0 40px rgba(59, 130, 246, 0.3);
      animation: glow-pulse 2s ease-in-out infinite;
    }

    @keyframes glow-pulse {
      0%, 100% { 
        box-shadow: 0 0 20px rgba(59, 130, 246, 0.6), 0 0 40px rgba(59, 130, 246, 0.3);
      }
      50% { 
        box-shadow: 0 0 30px rgba(59, 130, 246, 0.8), 0 0 60px rgba(59, 130, 246, 0.5);
      }
    }

    /* Hover effect only when button has text */
    .btn.send.has-text:hover:not(:disabled) {
      transform: translateY(-2px);
      box-shadow: 0 0 25px rgba(59, 130, 246, 0.7), 0 0 50px rgba(59, 130, 246, 0.4);
      background: linear-gradient(135deg, #3B82F6 0%, #2563EB 100%);
    }

    /* Gray hover effect when button is empty */
    .btn.send:not(.has-text):hover:not(:disabled) {
      transform: translateY(-2px);
      background: linear-gradient(135deg, #8b95a1 0%, #7e8894 100%);
      box-shadow: 0 4px 12px rgba(160, 174, 192, 0.3);
    }

    .btn.send:active:not(:disabled) {
      transform: translateY(0);
      box-shadow: 0 2px 8px rgba(72, 187, 120, 0.3);
      background: linear-gradient(135deg, #48BB78 0%, #68D391 100%);
    }

    .btn.send:disabled {
      opacity: 0.6;
      cursor: not-allowed;
      transform: none !important;
      box-shadow: 0 2px 8px rgba(59, 130, 246, 0.2);
      background: linear-gradient(135deg, #a0aec0 0%, #9ca3af 100%);
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }

    /* Examples section */
    .examples {
      background: rgba(255, 255, 255, 0.7);
      border: 1px solid rgba(226, 232, 240, 0.8);
      border-radius: 16px;
      padding: 24px;
      margin: 20px 0;
      backdrop-filter: blur(10px);
      box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
    }

    .examples h3 {
      margin: 0 0 16px 0;
      color: #2d3748;
      font-size: 16px;
      font-weight: 600;
    }

    .examples ul {
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 8px;
    }

    .examples li {
      padding: 12px 16px;
      background: rgba(255, 255, 255, 0.9);
      border: 1px solid rgba(226, 232, 240, 0.6);
      border-radius: 12px;
      cursor: pointer;
      transition: all 0.2s ease;
      color: #4a5568;
      font-size: 14px;
      line-height: 1.4;
    }

    .examples li:hover {
      background: rgba(102, 126, 234, 0.05);
      border-color: #667eea;
      color: #667eea;
      transform: translateY(-1px);
      box-shadow: 0 2px 8px rgba(102, 126, 234, 0.1);
    }

    .icon-btn {
      border: 1px solid var(--border);
      background: transparent;
      color: var(--muted);
      border-radius: 8px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 28px;
      height: 28px;
      cursor: pointer;
    }

    .icon-btn:hover {
      color: var(--text);
      border-color: #9ca3af;
    }

    .reactions {
      display: flex;
      gap: 6px;
      align-items: center;
      margin: 6px 0 0 0;
    }

    .loading {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
      color: var(--muted);
    }

    .dataset-item {
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .dataset-item:hover {
      background: rgba(255, 255, 255, 0.05);
      border-color: var(--brand);
    }

    .dataset-title {
      font-weight: 600;
      margin-bottom: 4px;
    }

    .dataset-description {
      font-size: 12px;
      color: var(--muted);
      line-height: 1.4;
    }

    /* Azure Maps Control Styling - Match Segoe UI font */
    .atlas-control-container button,
    .atlas-control-container .atlas-control-button,
    .atlas-control-container .atlas-layer-legend-label,
    .atlas-control-container {
      font-family: "Segoe UI", "Segoe UI Variable Text", -apple-system, BlinkMacSystemFont, system-ui !important;
    }

    /* Style control dropdown styling */
    .atlas-control-container .atlas-control-style-list {
      font-family: "Segoe UI", "Segoe UI Variable Text", -apple-system, BlinkMacSystemFont, system-ui !important;
    }

    /* Hide map attribution completely (TomTom, EarthStar Geographics, etc.) */
    .azure-maps-copyright,
    .mapboxgl-ctrl-bottom-center,
    .maplibregl-ctrl-bottom-center,
    .mapboxgl-ctrl-attrib,
    .maplibregl-ctrl-attrib,
    div[class*="copyright"],
    div[class*="attribution"],
    .mapboxgl-ctrl-attrib-inner,
    .maplibregl-ctrl-attrib-inner {
      display: none !important;
      visibility: hidden !important;
      opacity: 0 !important;
    }

    /* Hide default Azure Maps logo if it interferes */
    .azure-maps-logo-container {
      display: none !important;
    }
  `}</style>
);
