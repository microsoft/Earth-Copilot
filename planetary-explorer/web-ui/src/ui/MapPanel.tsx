// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useEffect, useRef } from 'react';
import axios from 'axios';
import type { CollectionInfo } from './App';

declare const atlas: any;

export default function MapPanel({ geojson, selected }: { geojson: any | null; selected: CollectionInfo | null }) {
  const mapRef = useRef<any>(null);
  const dsRef = useRef<any>(null);

  useEffect(() => {
    async function init() {
      const cfg = await axios.get('/maps-config').then(r => r.data);
      const map = new atlas.Map('map', {
        center: [-95.7129, 37.0902],
        zoom: 3,
        style: 'satellite',
        authOptions: { authType: 'subscriptionKey', subscriptionKey: cfg.subscriptionKey },
      });
      map.events.add('ready', () => {
        const ds = new atlas.source.DataSource();
        map.sources.add(ds);
        map.layers.add(new atlas.layer.PolygonLayer(ds, null, { fillColor: 'rgba(255,165,0,0.2)', fillOpacity: 0.7 }));
        map.layers.add(new atlas.layer.LineLayer(ds, null, { strokeColor: 'orange', strokeWidth: 2 }));
        dsRef.current = ds;
      });
      mapRef.current = map;
    }
    init();
  }, []);

  useEffect(() => {
    if (!geojson || !dsRef.current) return;
    dsRef.current.clear();
    for (const f of geojson.features || []) {
      dsRef.current.add(f);
    }
    // Compute union bbox of ALL features, not just the first one
    if (geojson.features?.length > 0 && mapRef.current) {
      let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity;
      for (const f of geojson.features) {
        if (f.bbox && f.bbox.length >= 4) {
          minLon = Math.min(minLon, f.bbox[0]);
          minLat = Math.min(minLat, f.bbox[1]);
          maxLon = Math.max(maxLon, f.bbox[2]);
          maxLat = Math.max(maxLat, f.bbox[3]);
        }
      }
      if (minLon !== Infinity) {
        mapRef.current.setCamera({ bounds: [minLon, minLat, maxLon, maxLat], padding: 50 });
      }
    }
  }, [geojson]);

  useEffect(() => {
    if (selected?.extent_bbox && mapRef.current) {
      const b = selected.extent_bbox;
      mapRef.current.setCamera({ bounds: [b[0], b[1], b[2], b[3]], padding: 50 });
    }
  }, [selected]);

  return <div id="map"></div>;
}
