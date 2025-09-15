import React, { useMemo, useState } from 'react';
import axios from 'axios';
import type { CollectionLite, CollectionInfo } from './App';

export default function CatalogPanel({
  collections,
  onRefresh,
  onSelect,
}: {
  collections: CollectionLite[];
  onRefresh: () => void;
  onSelect: (c: CollectionInfo) => void;
}) {
  const [q, setQ] = useState('');

  const filtered = useMemo(
    () => collections.filter(c => (c.title || '').toLowerCase().includes(q.toLowerCase()) || c.id.toLowerCase().includes(q.toLowerCase())),
    [collections, q]
  );

  async function pick(id: string) {
    const res = await axios.get(`/collections/${encodeURIComponent(id)}`);
    onSelect(res.data);
  }

  return (
    <div>
      <div className="row" style={{ marginBottom: 8 }}>
        <input className="input" placeholder="Search collections..." value={q} onChange={e => setQ(e.target.value)} />
        <button onClick={onRefresh}>Refresh</button>
      </div>
      <div className="list">
        {filtered.map(c => (
          <div key={c.id} className="list-item" onClick={() => pick(c.id)}>
            {c.title} <span style={{ color: '#888' }}>({c.id})</span>
          </div>
        ))}
      </div>
    </div>
  );
}
