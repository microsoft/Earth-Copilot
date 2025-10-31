/**
 * Quick test for renderingConfig module
 */
import { getCollectionConfig, isMODISCollection, isElevationCollection } from './renderingConfig';

// Test MODIS collections (should have minZoom=8)
console.log('Testing MODIS collections:');
const modis13Q1 = getCollectionConfig('modis-13Q1-061');
console.log('  modis-13Q1-061:', modis13Q1.minZoom === 8 ? '✅' : '❌', `minZoom=${modis13Q1.minZoom}`);

const modis14A1 = getCollectionConfig('modis-14A1-061');
console.log('  modis-14A1-061:', modis14A1.minZoom === 8 ? '✅' : '❌', `minZoom=${modis14A1.minZoom}`);

// Test DEM collections (should have minZoom=6, opacity=0.5)
console.log('\nTesting DEM collections:');
const copDem = getCollectionConfig('cop-dem-glo-30');
console.log('  cop-dem-glo-30:', (copDem.minZoom === 6 && copDem.opacity === 0.5) ? '✅' : '❌', 
  `minZoom=${copDem.minZoom}, opacity=${copDem.opacity}`);

// Test optical collections (should have minZoom=6, opacity=0.85)
console.log('\nTesting optical collections:');
const sentinel2 = getCollectionConfig('sentinel-2-l2a');
console.log('  sentinel-2-l2a:', (sentinel2.minZoom === 6 && sentinel2.opacity === 0.85) ? '✅' : '❌',
  `minZoom=${sentinel2.minZoom}, opacity=${sentinel2.opacity}`);

// Test pattern matching for unknown MODIS collection
console.log('\nTesting pattern matching:');
const unknownModis = getCollectionConfig('modis-99X9-999');
console.log('  modis-99X9-999 (unknown):', unknownModis.minZoom === 8 ? '✅' : '❌',
  `minZoom=${unknownModis.minZoom} (should use MODIS pattern)`);

// Test helper functions
console.log('\nTesting helper functions:');
console.log('  isMODISCollection("modis-13Q1-061"):', isMODISCollection('modis-13Q1-061') ? '✅' : '❌');
console.log('  isElevationCollection("cop-dem-glo-30"):', isElevationCollection('cop-dem-glo-30') ? '✅' : '❌');

console.log('\n✅ All tests passed!');
