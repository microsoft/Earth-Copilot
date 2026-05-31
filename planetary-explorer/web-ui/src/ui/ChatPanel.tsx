// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useRef, useState } from 'react';
import axios from 'axios';
import type { CollectionInfo } from './App';
import { API_BASE_URL } from '../services/api';

export default function ChatPanel({ selected, onGeojson }: { selected: CollectionInfo | null; onGeojson: (g: any) => void }) {
  const [messages, setMessages] = useState<{ role: 'user' | 'assistant'; content: string }[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);

  async function send() {
    const content = inputRef.current?.value.trim();
    if (!content) return;
    inputRef.current!.value = '';
    setMessages((m) => [...m, { role: 'user', content }]);

    setLoading(true);
    try {
      // Use API_BASE_URL for correct backend routing in all environments
      const res = await axios.post(`${API_BASE_URL}/api/query`, {
        query: content
      });
      const data = res.data;
      console.log('Docker response:', data);

      // Extract response from Docker function app format
      const assistant = data.results?.response || data.response || '(no response)';
      setMessages((m) => [...m, { role: 'assistant', content: assistant }]);

      // Handle map data if present
      if (data.results?.map_data) {
        onGeojson(data.results.map_data);
      }
    } catch (e: any) {
      console.error('Chat error:', e);
      setMessages((m) => [...m, { role: 'assistant', content: `Failed to send message. Error: ${e.message}` }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="chat-history">
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>{m.content}</div>
        ))}
      </div>
      <div className="row">
        <input className="input" ref={inputRef} placeholder={selected ? `Ask about ${selected.id}...` : 'Ask about satellite data...'} />
        <button onClick={send} disabled={loading}>Send</button>
      </div>
    </div>
  );
}
