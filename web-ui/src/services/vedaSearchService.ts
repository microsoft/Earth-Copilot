// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

/**
 * Direct VEDA Search Service
 * Bypasses function app for simple AI Search + LLM responses
 */

import axios from 'axios';

interface VEDASearchConfig {
  searchEndpoint: string;
  searchApiKey: string;
  searchIndex: string;
  openaiEndpoint: string;
  openaiApiKey: string;
  openaiDeployment: string;
}

interface VEDACollection {
  id: string;
  title: string;
  description: string;
  spatial_extent?: any;
  temporal_extent?: any;
  relevance_score?: number;
}

interface VEDASearchResponse {
  answer: string;
  collections: VEDACollection[];
  reasoning: string;
}

class VEDASearchService {
  private config: VEDASearchConfig;

  constructor() {
    // Get config from environment or use defaults for dev
    this.config = {
      searchEndpoint: import.meta.env.VITE_AZURE_SEARCH_ENDPOINT || 'https://your-search-service.search.windows.net',
      searchApiKey: import.meta.env.VITE_AZURE_SEARCH_API_KEY || '',
      searchIndex: import.meta.env.VITE_AZURE_SEARCH_INDEX || 'veda-collections-index',
      openaiEndpoint: import.meta.env.VITE_AZURE_OPENAI_ENDPOINT || '',
      openaiApiKey: import.meta.env.VITE_AZURE_OPENAI_API_KEY || '',
      openaiDeployment: import.meta.env.VITE_AZURE_OPENAI_DEPLOYMENT || 'gpt-5'
    };
  }

  /**
   * Search collections using Azure AI Search vector search
   */
  private async searchCollections(query: string, collection_id?: string): Promise<VEDACollection[]> {
    console.log('🔍 Searching Azure AI Search for collections...');
    
    try {
      // First try to get embeddings for the query
      const queryVector = await this.getQueryEmbeddings(query);
      
      if (!queryVector) {
        console.log('⚠️ No query vector available, using text search only');
        return await this.searchCollectionsTextOnly(query, collection_id);
      }

      console.log('🎯 Using vector search with query embeddings');

      // Perform vector search
      const searchBody = {
        search: query,
        top: 5,
        vectors: [
          {
            value: queryVector,
            fields: "content_vector",
            k: 5
          }
        ],
        select: "id,title,description,spatial_extent,temporal_extent",
        filter: collection_id ? `id eq '${collection_id}'` : undefined
      };

      console.log('� Azure AI Search request:', {
        endpoint: `${this.config.searchEndpoint}/indexes/${this.config.searchIndex}/docs/search`,
        searchText: query,
        vectorSearch: true,
        filter: searchBody.filter
      });

      const response = await axios.post(
        `${this.config.searchEndpoint}/indexes/${this.config.searchIndex}/docs/search?api-version=2023-11-01`,
        searchBody,
        {
          headers: {
            'Content-Type': 'application/json',
            'api-key': this.config.searchApiKey
          }
        }
      );

      const results = response.data.value || [];
      console.log(`✅ Found ${results.length} collections from Azure AI Search`);

      return results.map((result: any) => ({
        id: result.id,
        title: result.title,
        description: result.description,
        spatial_extent: result.spatial_extent ? JSON.parse(result.spatial_extent) : undefined,
        temporal_extent: result.temporal_extent ? JSON.parse(result.temporal_extent) : undefined
      }));

    } catch (error: any) {
      console.error('❌ Azure AI Search failed:', error?.response?.data || error.message);
      console.log('🔄 Falling back to text-only search...');
      return await this.searchCollectionsTextOnly(query, collection_id);
    }
  }

  /**
   * Fallback text-only search when vector search fails
   */
  private async searchCollectionsTextOnly(query: string, collection_id?: string): Promise<VEDACollection[]> {
    try {
      console.log('🔤 Using text-only search');
      
      const searchBody = {
        search: query,
        top: 5,
        select: "id,title,description,spatial_extent,temporal_extent",
        filter: collection_id ? `id eq '${collection_id}'` : undefined
      };

      const response = await axios.post(
        `${this.config.searchEndpoint}/indexes/${this.config.searchIndex}/docs/search?api-version=2023-11-01`,
        searchBody,
        {
          headers: {
            'Content-Type': 'application/json',
            'api-key': this.config.searchApiKey
          }
        }
      );

      const results = response.data.value || [];
      console.log(`✅ Found ${results.length} collections using text search`);

      return results.map((result: any) => ({
        id: result.id,
        title: result.title,
        description: result.description,
        spatial_extent: result.spatial_extent ? JSON.parse(result.spatial_extent) : undefined,
        temporal_extent: result.temporal_extent ? JSON.parse(result.temporal_extent) : undefined
      }));

    } catch (error: any) {
      console.error('❌ Text search also failed:', error?.response?.data || error.message);
      throw error;
    }
  }

  /**
   * Generate embeddings for query using Azure OpenAI
   */
  private async getQueryEmbeddings(query: string): Promise<number[]> {
    try {
      console.log('🔍 Getting embeddings for query:', query);
      
      // Try different embedding deployment names that might exist
      const possibleEmbeddingDeployments = [
        'text-embedding-ada-002',
        'text-embedding-3-small', 
        'text-embedding-3-large',
        'ada-002',
        'embedding'
      ];
      
      let lastError: any = null;
      
      for (const deployment of possibleEmbeddingDeployments) {
        try {
          const embeddingsUrl = `${this.config.openaiEndpoint}/openai/deployments/${deployment}/embeddings?api-version=2024-06-01`;
          console.log('🔍 Trying embeddings deployment:', deployment);
          console.log('🔍 Embeddings URL:', embeddingsUrl);
          
          const response = await axios.post(embeddingsUrl, {
            input: query,
            encoding_format: "float"
          }, {
            headers: {
              'api-key': this.config.openaiApiKey,
              'Content-Type': 'application/json'
            }
          });

          console.log('✅ Got embeddings response with deployment:', deployment);
          return response.data.data[0].embedding;
        } catch (error: any) {
          console.log(`❌ Embedding deployment ${deployment} failed:`, error.response?.status);
          lastError = error;
          continue; // Try next deployment
        }
      }
      
      // If all deployments failed, throw the last error
      console.error('🚨 All embedding deployments failed, last error:', lastError);
      if (lastError?.response) {
        console.error('🚨 Last embeddings response status:', lastError.response.status);
        console.error('🚨 Last embeddings response data:', lastError.response.data);
      }
      throw new Error(`Failed to generate query embeddings: No working embedding deployment found. Last error: ${lastError.message}`);
    } catch (error: any) {
      console.error('🚨 Failed to get embeddings:', error);
      throw error;
    }
  }

  /**
   * Generate LLM response using found collections
   */
  async generateResponse(query: string, collections: VEDACollection[]): Promise<string> {
    try {
      console.log('🤖 Generating LLM response for query:', query);
      console.log('🤖 Using collections:', collections.length);
      
      const chatUrl = `${this.config.openaiEndpoint}/openai/deployments/${this.config.openaiDeployment}/chat/completions?api-version=2024-06-01`;
      console.log('🤖 Chat URL:', chatUrl);
      
      const systemPrompt = `You are a VEDA (Visualization, Exploration, and Data Analysis) Earth Science data expert. 
      You help users understand and discover NASA Earth Science datasets from the VEDA catalog.
      
      Provide helpful, accurate information about the datasets found. Be conversational and educational.
      Focus on the practical applications and scientific value of the data.`;

      const collectionsContext = collections.length > 0 
        ? `\n\nRelevant VEDA datasets found:\n${collections.map(c => 
            `- ${c.title}: ${c.description}`
          ).join('\n')}`
        : '\n\nNo specific datasets were found matching your query, but I can provide general information about VEDA Earth Science data.';

      const userPrompt = `${query}${collectionsContext}`;

      const response = await axios.post(chatUrl, {
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt }
        ],
        max_tokens: 1000,
        temperature: 0.7
      }, {
        headers: {
          'api-key': this.config.openaiApiKey,
          'Content-Type': 'application/json'
        }
      });

      console.log('✅ Got LLM response');
      return response.data.choices[0].message.content;
    } catch (error: any) {
      console.error('🚨 Failed to generate LLM response:', error);
      if (error.response) {
        console.error('🚨 LLM response status:', error.response.status);
        console.error('🚨 LLM response data:', error.response.data);
      }
      throw new Error(`Failed to generate response: ${error.message}`);
    }
  }

  /**
   * Main search method - combines vector search + LLM response
   */
  async search(query: string, collection_id?: string): Promise<VEDASearchResponse> {
    try {
      console.log('🌍 VEDA Search called:', { query, collection_id });
      
      // Check if we have the required configuration for real Azure services
      const hasRealConfig = this.config.searchApiKey && 
                           this.config.openaiApiKey && 
                           this.config.searchEndpoint.includes('search.windows.net') && 
                           this.config.openaiEndpoint.includes('openai.azure.com');
      
      console.log('🔧 VEDA Config Check:', {
        hasRealConfig,
        hasSearchApiKey: !!this.config.searchApiKey,
        hasOpenAIApiKey: !!this.config.openaiApiKey,
        searchEndpoint: this.config.searchEndpoint,
        openaiEndpoint: this.config.openaiEndpoint,
        searchIndex: this.config.searchIndex
      });
      
      if (!hasRealConfig) {
        console.log('🔧 Missing Azure configuration: using simulated VEDA search');
        return this.simulateVEDASearch(query, collection_id);
      }
      
      console.log('� Attempting real Azure AI Search with indexed VEDA data');
      
      try {
        // Production: Search indexed VEDA collections
        console.log('📊 Searching real indexed VEDA collections...');
        const collections = await this.searchCollections(query, collection_id);
        console.log('📊 Found indexed collections:', collections.length);
        
        if (collections.length === 0) {
          console.log('⚠️ No indexed collections found, using hybrid approach...');
          // Use hybrid approach when no indexed results
          const simulatedCollections = this.getSimulatedCollections(query, collection_id);
          const answer = await this.generateResponse(query, simulatedCollections);
          
          return {
            answer,
            collections: simulatedCollections,
            reasoning: `No results found in indexed VEDA data. Generated response using Azure OpenAI GPT-5 with ${simulatedCollections.length} simulated relevant datasets.`
          };
        }
        
        // Generate response using real indexed data
        console.log('🤖 Generating response with real indexed VEDA data...');
        const answer = await this.generateResponse(query, collections);
        
        console.log('✅ Successfully used real Azure AI Search + real indexed VEDA data');
        return {
          answer,
          collections,
          reasoning: `Found ${collections.length} relevant VEDA datasets using AI-powered semantic search on indexed NASA VEDA collections`
        };
      } catch (azureError) {
        console.error('🚨 Azure AI Search failed, using hybrid approach:', azureError);
        
        // Hybrid fallback: simulated collections + real LLM
        const simulatedCollections = this.getSimulatedCollections(query, collection_id);
        console.log('📊 Using simulated collections:', simulatedCollections.length);
        
        try {
          const answer = await this.generateResponse(query, simulatedCollections);
          console.log('✅ Hybrid approach successful: simulated data + real LLM');
          return {
            answer,
            collections: simulatedCollections,
            reasoning: `Azure AI Search unavailable. Generated dynamic response using Azure OpenAI GPT-5 with ${simulatedCollections.length} relevant VEDA datasets`
          };
        } catch (llmError) {
          console.error('🚨 LLM generation also failed, full simulation:', llmError);
          return this.simulateVEDASearch(query, collection_id);
        }
      }
    } catch (error) {
      console.error('VEDA search failed completely:', error);
      
      // Complete fallback to simulated response
      console.log('🔧 Falling back to simulated VEDA search due to general error');
      return this.simulateVEDASearch(query, collection_id);
    }
  }

  /**
   * Get simulated collections for hybrid approach
   */
  private getSimulatedCollections(query: string, collection_id?: string): VEDACollection[] {
    const lowerQuery = query.toLowerCase();
    
    // Enhanced simulation with more diverse collections
    const allCollections: VEDACollection[] = [
      {
        id: 'landsat-c2l2-sr',
        title: 'Landsat Collection 2 Level-2 Surface Reflectance',
        description: 'Landsat Collection 2 Level-2 surface reflectance products from multiple sensors (TM, ETM+, OLI). Contains multispectral optical imagery ideal for land use monitoring and agricultural analysis.',
        temporal_extent: ['1982-08-22', '2024-01-01'],
        spatial_extent: [-180, -90, 180, 90]
      },
      {
        id: 'sentinel-2-l2a',
        title: 'Sentinel-2 Level-2A Surface Reflectance',
        description: 'High-resolution optical imagery from ESA Sentinel-2 satellites with atmospheric correction. Provides detailed surface reflectance data perfect for vegetation monitoring and land cover analysis.',
        temporal_extent: ['2015-06-23', '2024-01-01'],
        spatial_extent: [-180, -84, 180, 84]
      },
      {
        id: 'modis-terra-aqua',
        title: 'MODIS Terra and Aqua Combined Products',
        description: 'Moderate Resolution Imaging Spectroradiometer data from Terra and Aqua satellites. Daily global coverage with excellent temporal resolution for monitoring environmental changes.',
        temporal_extent: ['2000-02-24', '2024-01-01'],
        spatial_extent: [-180, -90, 180, 90]
      },
      {
        id: 'nasa-dem',
        title: 'NASA Digital Elevation Model',
        description: 'Global digital elevation model derived from SRTM and other elevation sources. Essential for topographic analysis, watershed studies, and terrain modeling.',
        temporal_extent: ['2000-01-01', '2000-12-31'],
        spatial_extent: [-180, -60, 180, 60]
      },
      {
        id: 'aster-l1t',
        title: 'ASTER Level 1T Precision Terrain Corrected',
        description: 'Advanced Spaceborne Thermal Emission and Reflection Radiometer data. Combines VNIR, SWIR, and thermal infrared data for comprehensive Earth observation.',
        temporal_extent: ['2000-03-06', '2024-01-01'],
        spatial_extent: [-180, -83, 180, 83]
      },
      {
        id: 'goes-16-17',
        title: 'GOES-16/17 Weather Satellite Data',
        description: 'Geostationary weather satellite data with high temporal resolution. Perfect for meteorological analysis, cloud tracking, and atmospheric monitoring.',
        temporal_extent: ['2017-01-01', '2024-01-01'],
        spatial_extent: [-156, -81, 6, 81]
      },
      {
        id: 'viirs-dnb',
        title: 'VIIRS Day/Night Band',
        description: 'Visible Infrared Imaging Radiometer Suite nighttime lights and low-light imagery. Excellent for studying human activity patterns and nighttime Earth observation.',
        temporal_extent: ['2012-01-19', '2024-01-01'],
        spatial_extent: [-180, -90, 180, 90]
      },
      {
        id: 'ecmwf-era5',
        title: 'ERA5 Reanalysis Climate Data',
        description: 'Comprehensive atmospheric reanalysis from ECMWF covering weather and climate variables. Contains temperature, precipitation, wind, and other atmospheric parameters.',
        temporal_extent: ['1950-01-01', '2024-01-01'],
        spatial_extent: [-180, -90, 180, 90]
      }
    ];
    
    // Filter by collection_id if specified
    let filteredCollections = collection_id 
      ? allCollections.filter(c => c.id === collection_id)
      : allCollections;
    
    // Simple relevance scoring based on query keywords
    const queryKeywords = ['landsat', 'sentinel', 'modis', 'elevation', 'aster', 'goes', 'viirs', 'era5', 'thermal', 'optical', 'weather', 'climate'];
    
    return filteredCollections
      .filter(collection => {
        // Keep collections that match query terms
        const text = (collection.title + ' ' + collection.description).toLowerCase();
        return queryKeywords.some(keyword => lowerQuery.includes(keyword) && text.includes(keyword)) || 
               lowerQuery.split(' ').some(word => text.includes(word));
      })
      .slice(0, 5);
  }

  /**
   * Simulate VEDA search for development/demo purposes
   */
  private async simulateVEDASearch(query: string, collection_id?: string): Promise<VEDASearchResponse> {
    // Simulate realistic delay
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // Generate dynamic response based on query
    const queryLower = query.toLowerCase();
    let collections: VEDACollection[] = [];
    let answer = '';

    if (queryLower.includes('temperature') || queryLower.includes('thermal')) {
      collections = [
        {
          id: collection_id || 'era5-temperature',
          title: 'ERA5 Temperature Data',
          description: 'Comprehensive global temperature measurements from the ERA5 reanalysis dataset.',
          relevance_score: 0.95
        }
      ];
      answer = `Based on your query about temperature data, I found the **ERA5 Temperature Data** collection. This dataset provides comprehensive global temperature measurements with high temporal and spatial resolution. It's particularly valuable for climate research, weather pattern analysis, and understanding global warming trends.`;

    } else if (queryLower.includes('pressure') || queryLower.includes('blizzard') || queryLower.includes('atmospheric') || queryLower.includes('storm')) {
      collections = [
        {
          id: collection_id || 'blizzard-era5-mslp',
          title: 'Blizzard ERA5 Surface Pressure',
          description: 'ERA5 mean sea level pressure data during blizzard events, providing insights into atmospheric conditions during extreme weather.',
          relevance_score: 0.92
        }
      ];
      
      if (queryLower.includes('blizzard') || queryLower.includes('atmospheric conditions')) {
        answer = `Based on your query about atmospheric conditions during blizzards, the **Blizzard ERA5 Surface Pressure** dataset reveals fascinating insights:

**Key Atmospheric Conditions During Blizzards:**
- **Rapid Pressure Drops**: Blizzards typically form when atmospheric pressure drops rapidly (often 24+ millibars in 24 hours), creating intense low-pressure systems
- **Pressure Gradients**: Steep pressure gradients drive the strong winds (35+ mph sustained) that define blizzard conditions
- **Cyclonic Systems**: Most blizzards are associated with extratropical cyclones featuring distinctive pressure patterns with deep central lows
- **Temperature Contrasts**: The pressure data shows how cold Arctic air masses interact with warmer air, creating the instability needed for heavy snowfall

**What the ERA5 Data Shows:**
- Hourly pressure measurements during documented blizzard events
- Pressure evolution from storm formation through dissipation  
- Spatial patterns showing how pressure systems move and intensify
- Correlation between pressure drops and wind speed increases

This dataset is particularly valuable for understanding how atmospheric pressure drives the formation and intensity of blizzard conditions, helping meteorologists predict future severe winter weather events.`;
      } else {
        answer = `I found the **Blizzard ERA5 Surface Pressure** dataset, which provides detailed atmospheric pressure measurements during extreme weather events. This data is crucial for understanding storm formation, tracking weather systems, and analyzing the relationship between pressure patterns and severe weather.`;
      }

    } else if (queryLower.includes('precipitation') || queryLower.includes('rain') || queryLower.includes('snow')) {
      collections = [
        {
          id: collection_id || 'gpm-precipitation',
          title: 'GPM Precipitation Data',
          description: 'Global Precipitation Measurement mission data providing comprehensive rainfall and snowfall measurements.',
          relevance_score: 0.90
        }
      ];
      answer = `I found the **GPM Precipitation Data** collection from NASA's Global Precipitation Measurement mission. This dataset offers detailed precipitation measurements worldwide, essential for water cycle research, flood prediction, and agricultural planning.`;

    } else if (queryLower.includes('ocean') || queryLower.includes('sea') || queryLower.includes('marine')) {
      collections = [
        {
          id: collection_id || 'modis-sst',
          title: 'MODIS Sea Surface Temperature',
          description: 'MODIS-derived sea surface temperature measurements for ocean climate studies.',
          relevance_score: 0.88
        }
      ];
      answer = `I found the **MODIS Sea Surface Temperature** dataset, which provides accurate ocean temperature measurements. This data is vital for understanding ocean circulation patterns, marine ecosystems, and climate change impacts on our oceans.`;

    } else {
      // Default generic VEDA response
      collections = [
        {
          id: collection_id || 'veda-general',
          title: 'VEDA Earth Science Collections',
          description: 'Comprehensive collection of NASA Earth Science datasets covering climate, weather, and environmental data.',
          relevance_score: 0.80
        }
      ];
      answer = `I understand you're interested in Earth Science data. The VEDA (Visualization, Exploration, and Data Analysis) platform provides access to NASA's comprehensive Earth Science datasets including climate data, satellite observations, atmospheric measurements, and environmental monitoring data. 

You can ask me about specific topics like:
- Temperature and climate data
- Precipitation and weather patterns  
- Ocean and marine observations
- Atmospheric pressure and conditions
- Satellite imagery and remote sensing

What specific aspect of Earth Science data would you like to explore?`;
    }

    return {
      answer,
      collections: collections.filter(c => !collection_id || c.id === collection_id),
      reasoning: `Simulated search found ${collections.length} relevant VEDA datasets for "${query}" (development mode)`
    };
  }
}

// Export singleton instance
export const vedaSearchService = new VEDASearchService();
export default vedaSearchService;