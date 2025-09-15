// Quick test of VEDA search service
import vedaSearchService from '../src/services/vedaSearchService.js';

async function testVEDASearch() {
  console.log('🧪 Testing VEDA Search Service...');
  
  try {
    const result = await vedaSearchService.search('Tell me about Blizzard ERA5 Surface Pressure', 'blizzard-era5-mslp');
    console.log('✅ VEDA Search Success:', result);
    console.log('📊 Collections found:', result.collections.length);
    console.log('💬 Answer preview:', result.answer.substring(0, 200) + '...');
  } catch (error) {
    console.error('❌ VEDA Search Failed:', error);
  }
}

testVEDASearch();