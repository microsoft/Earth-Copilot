// Test script to validate tile URL generation
import { TileUrlGenerator } from '../src/utils/tileUrlGenerator';

// Test cases for different collection types
const testCases = [
  {
    name: 'Sentinel-2 Single Item',
    config: {
      collection: 'sentinel-2-l2a',
      item: 'S2A_MSIL2A_20230815T180921_N0509_R027_T11SMS_20230816T002953',
      assets: ['visual']
    }
  },
  {
    name: 'Sentinel-1 Radar',
    config: {
      collection: 'sentinel-1-rtc',
      item: 'S1A_IW_RTCP_20230815T123456',
      assets: ['vh']
    }
  },
  {
    name: 'Landsat Collection 2',
    config: {
      collection: 'landsat-c2-l2',
      item: 'LC08_L2SP_044034_20230815_20230823_02_T1',
      assets: ['visual']
    }
  },
  {
    name: 'Climate Data - Daymet',
    config: {
      collection: 'daymet-daily-na',
      item: 'daymet-daily-na_2023_215',
      assets: ['tmax']
    }
  }
];

console.log('🧪 Testing Tile URL Generation...\n');

testCases.forEach(testCase => {
  console.log(`📋 ${testCase.name}:`);
  
  try {
    const itemUrl = TileUrlGenerator.generateItemTileUrl(testCase.config);
    console.log(`  ✅ Item Tile: ${itemUrl}`);
    
    const previewUrl = TileUrlGenerator.generatePreviewUrl(testCase.config);
    console.log(`  ✅ Preview: ${previewUrl}`);
    
    const tileJsonUrl = TileUrlGenerator.generateTileJsonUrl(testCase.config);
    console.log(`  ✅ TileJSON: ${tileJsonUrl}`);
  } catch (error) {
    console.log(`  ❌ Error: ${error}`);
  }
  
  console.log('');
});

console.log('🧪 Testing Adaptive URL Generation...\n');

const adaptiveTestCases = [
  {
    name: 'Single Item Adaptive',
    collection: 'sentinel-2-l2a',
    items: [{ id: 'test-item', collection: 'sentinel-2-l2a', datetime: '2023-08-15' }]
  },
  {
    name: 'Multiple Items Mosaic',
    collection: 'landsat-c2-l2',
    items: [
      { id: 'item1', collection: 'landsat-c2-l2', datetime: '2023-08-15' },
      { id: 'item2', collection: 'landsat-c2-l2', datetime: '2023-08-16' }
    ],
    bbox: [-123, 47, -122, 48]
  }
];

adaptiveTestCases.forEach(testCase => {
  console.log(`📋 ${testCase.name}:`);
  
  try {
    const adaptiveUrl = TileUrlGenerator.generateAdaptiveTileUrl(
      testCase.collection,
      testCase.items,
      testCase.bbox
    );
    console.log(`  ✅ Adaptive URL: ${adaptiveUrl}`);
  } catch (error) {
    console.log(`  ❌ Error: ${error}`);
  }
  
  console.log('');
});
