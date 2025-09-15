// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import CatalogPanel from './CatalogPanel';
import ChatPanel from './ChatPanel';
import MapPanel from './MapPanel';

export type CollectionLite = { id: string; title: string };
export type CollectionInfo = { id: string; title: string; description?: string; license?: string; extent_bbox?: number[] };

function useCollections() {
  return useQuery({
    queryKey: ['collections'],
    queryFn: async (): Promise<CollectionLite[]> => {
      const res = await axios.get('/collections');
      return res.data.collections;
    },
  });
}

export default function App() {
  const { data: collections = [], refetch } = useCollections();
  const [selected, setSelected] = useState<CollectionInfo | null>(null);
  const [geojson, setGeojson] = useState<any | null>(null);

  return (
    <div className="app">
      <div className="panel">
        <h2 className="h2">Planetary Computer Catalog</h2>
        <CatalogPanel
          collections={collections}
          onRefresh={() => refetch()}
          onSelect={setSelected}
        />
      </div>
      <MapPanel geojson={geojson} selected={selected} />
      <div className="panel right">
        <h2 className="h2">Earth Copilot</h2>
        <ChatPanel
          selected={selected}
          onGeojson={(g) => setGeojson(g)}
        />
      </div>
    </div>
  );
}
