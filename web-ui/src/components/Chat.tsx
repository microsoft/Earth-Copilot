// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState, useRef, useEffect } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { apiService, Dataset, ChatMessage, MapContext } from '../services/api';
import { enhanceMessageForMapVisualization, hasVisualizableData } from './EarthCopilotMapIntegration';
import vedaSearchService from '../services/vedaSearchService';

// Enhanced function to extract text from complex response objects
function extractTextFromResponse(content: any): string {
  console.log('🔍 extractTextFromResponse: Input type:', typeof content);
  console.log('🔍 extractTextFromResponse: Input content preview:', String(content).substring(0, 150) + '...');

  if (typeof content === 'string') {
    const contentStr = content;

    // Check if it's a ChatMessageContent object by looking for the specific pattern
    if (contentStr.includes('ChatMessageContent(') && contentStr.includes('ChatCompletionMessage(content=')) {
      console.log('🔍 extractTextFromResponse: Detected ChatMessageContent string format');
      console.log('🔍 extractTextFromResponse: String starts with:', contentStr.substring(0, 200));
      console.log('🔍 extractTextFromResponse: Looking for ChatCompletionMessage pattern...');

      // Use a very specific regex for the exact pattern we're seeing
      // This matches: ChatCompletionMessage(content='...content...'
      const messageContentMatch = contentStr.match(/ChatCompletionMessage\(content='([^']*(?:\\'[^']*)*?)'/s);
      if (messageContentMatch && messageContentMatch[1]) {
        console.log('🔍 extractTextFromResponse: ✅ Successfully extracted from ChatCompletionMessage');
        console.log('🔍 extractTextFromResponse: Extracted length:', messageContentMatch[1].length);
        let extracted = messageContentMatch[1];
        // Convert escaped characters back to normal
        extracted = extracted.replace(/\\n/g, '\n');
        extracted = extracted.replace(/\\'/g, "'");
        extracted = extracted.replace(/\\\\/g, '\\');
        return extracted;
      } else {
        console.log('🔍 extractTextFromResponse: ❌ ChatCompletionMessage regex did not match');
      }

      // Alternative: try to find content=' pattern anywhere in the string
      const generalContentMatch = contentStr.match(/content='([^']*(?:\\'[^']*)*?)'/s);
      if (generalContentMatch && generalContentMatch[1] && generalContentMatch[1].length > 100) {
        console.log('🔍 extractTextFromResponse: ✅ Found content using general pattern');
        console.log('🔍 extractTextFromResponse: Extracted length:', generalContentMatch[1].length);
        let extracted = generalContentMatch[1];
        extracted = extracted.replace(/\\n/g, '\n');
        extracted = extracted.replace(/\\'/g, "'");
        extracted = extracted.replace(/\\\\/g, '\\');
        return extracted;
      } else {
        console.log('🔍 extractTextFromResponse: ❌ General content pattern did not match or too short');
      }

      console.log('🔍 extractTextFromResponse: ❌ Could not extract content with regex patterns');
    } else {
      console.log('🔍 extractTextFromResponse: Not a ChatMessageContent format, treating as regular string');
    }

    // If it's just a regular string, return as-is
    return content;
  }

  if (Array.isArray(content)) {
    console.log('🔍 extractTextFromResponse: Processing array with', content.length, 'items');
    return content.map(item => extractTextFromResponse(item)).join('');
  }

  if (typeof content === 'object' && content !== null) {
    // Handle direct object access if the object has proper structure
    try {
      // Check if we can access properties directly (for proper object instances)
      if (content.items && Array.isArray(content.items)) {
        console.log('🔍 extractTextFromResponse: Processing items array directly');
        const extracted = content.items.map((item: any) => {
          if (item.text) return item.text;
          if (item.inner_content) return item.inner_content;
          return extractTextFromResponse(item);
        }).join('');
        if (extracted) return extracted;
      }

      // Handle inner_content structures
      if (content.inner_content) {
        if (typeof content.inner_content === 'string') return content.inner_content;
        if (content.inner_content.choices && Array.isArray(content.inner_content.choices)) {
          const choice = content.inner_content.choices[0];
          if (choice && choice.message && choice.message.content) {
            return choice.message.content;
          }
        }
        return extractTextFromResponse(content.inner_content);
      }

      // Handle direct properties
      if (content.text) return content.text;
      if (content.content) return content.content;
      if (content.message && content.message.content) return content.message.content;
    } catch (e) {
      console.log('🔍 extractTextFromResponse: Object property access failed, trying string conversion');
    }

    // Convert object to string and try regex extraction
    const contentStr = String(content);
    if (contentStr.includes('content=')) {
      const match = contentStr.match(/content='([^']*(?:\\'[^']*)*?)'/s);
      if (match && match[1] && match[1].length > 50) {
        console.log('🔍 extractTextFromResponse: ✅ Extracted from object string conversion');
        let extracted = match[1];
        extracted = extracted.replace(/\\n/g, '\n');
        extracted = extracted.replace(/\\'/g, "'");
        return extracted;
      }
    }
  }

  console.log('🔍 extractTextFromResponse: ❌ Fallback to string conversion');
  return String(content || '');
}

function renderMessageHTML(content: string): string {
  let s = String(content || '');
  // Remove/soften preview lines; we'll show imagery on the map
  s = s.replace(/^\s*Preview:\s*.*$/gmi, '(shown on map)');
  // Strip markdown image syntax ![alt](url) entirely
  s = s.replace(/!\[[^\]]*\]\((https?:[^)]+)\)/g, '(shown on map)');
  // Convert [text](url) to link
  s = s.replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  // Autolink plain URLs
  s = s.replace(/(https?:\/\/[\w\-._~:?#\[\]@!$&'()*+,;=%/]+)(?![^<]*>)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  
  // Convert numbered section headers like "1) Overview" or "2) Elevation" to bold headers
  s = s.replace(/^(\d+\))\s+(.+)$/gm, '<strong style="font-size: 1.1em; display: block; margin-top: 16px; margin-bottom: 8px; color: #1e3a8a;">$1 $2</strong>');
  
  // Convert markdown headers (## Header) to styled headers
  s = s.replace(/^#{2,3}\s+(.+)$/gm, '<strong style="font-size: 1.1em; display: block; margin-top: 16px; margin-bottom: 8px; color: #1e3a8a;">$1</strong>');
  
  // Convert bullet points to styled list items
  s = s.replace(/^[\s]*[-•]\s+(.+)$/gm, '<div style="margin-left: 20px; margin-bottom: 4px;">• $1</div>');
  
  // Convert markdown bold **text** to <strong>text</strong>
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Convert markdown italic *text* to <em>text</em>
  s = s.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  
  // Preserve line breaks (but not for lines we've already formatted)
  s = s.replace(/\n/g, '<br/>');
  return s;
}

interface ChatProps {
  selectedDataset: Dataset | null;
  chatMode: boolean;
  initialQuery?: string;
  onResponseReceived?: (responseData: any) => void;
  onRestartSession?: () => void;
  privateSearchTrigger?: any; // New prop to trigger private search
  currentPin?: { lat: number; lng: number } | null; // Pin location from map
  geointMode: boolean; // GEOINT analysis mode toggle (deprecated)
  mobilityAnalysisResult?: any; // Mobility analysis result from map
  selectedModule?: string; // Selected GEOINT module (terrain_analysis, mobility_analysis, building_damage)
  mapContext?: MapContext; // Map context for Chat Vision capability
  systemMessage?: string | null; // System messages from workflow
  onUserMessage?: (message: string) => boolean; // Callback when user sends message, returns true if intercepted
}

const Chat: React.FC<ChatProps> = ({ 
  selectedDataset, 
  chatMode, 
  initialQuery, 
  onResponseReceived, 
  onRestartSession, 
  privateSearchTrigger, 
  currentPin, 
  geointMode, 
  mobilityAnalysisResult, 
  selectedModule,
  mapContext,
  systemMessage,
  onUserMessage,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [feedback, setFeedback] = useState<Record<number, string>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [hasProcessedInitialQuery, setHasProcessedInitialQuery] = useState(false);
  const initialQueryRef = useRef(false);
  const [lastResponse, setLastResponse] = useState<string>('');
  // Add conversation ID to maintain context across messages
  const [conversationId] = useState(() => `web-session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`);
  
  // VEDA search mode state
  const [isVedaMode, setIsVedaMode] = useState(false);
  const [currentCollectionId, setCurrentCollectionId] = useState<string | null>(null);

  // Add injection message when dataset is selected
  useEffect(() => {
    if (selectedDataset && chatMode) {
      const injectionMessage: ChatMessage = {
        role: 'assistant',
        content: `You're chatting with ${selectedDataset.title || selectedDataset.id}. Ask a question about it.\n\nTip: include a location/area and date range (e.g., 2024-01-01/2024-06-30).`,
        timestamp: new Date()
      };
      setMessages([injectionMessage]);
    }
  }, [selectedDataset, chatMode]);
  
  // Handle system messages from workflow (modules menu, module selection)
  useEffect(() => {
    if (systemMessage) {
      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: systemMessage,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, assistantMessage]);
    }
  }, [systemMessage]);
  
  // Handle GEOINT module selection and analysis results from map
  useEffect(() => {
    if (!mobilityAnalysisResult) return;
    
    if (mobilityAnalysisResult.type === 'info') {
      // Show informational message (e.g., "Please select a module", "Pin Mode Activated")
      const infoMessage: ChatMessage = {
        role: 'assistant',
        content: mobilityAnalysisResult.message,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, infoMessage]);
    } else if (mobilityAnalysisResult.type === 'thinking') {
      // Show "thinking" animation message - this will be replaced by actual result
      const thinkingMessage: ChatMessage = {
        role: 'assistant',
        content: '🤖 Thinking...',
        timestamp: new Date(),
        isThinking: true  // Flag to show loading indicator
      };
      setMessages(prev => [...prev, thinkingMessage]);
    } else if (mobilityAnalysisResult.type === 'assistant') {
      // Replace the last "thinking" message with the actual result
      setMessages(prev => {
        // Remove the last message if it's a "thinking" message
        const filtered = prev.filter((msg, idx) => {
          if (idx === prev.length - 1 && msg.isThinking) {
            return false;  // Remove thinking message
          }
          return true;
        });
        // Add the actual result
        return [...filtered, {
          role: 'assistant',
          content: mobilityAnalysisResult.message,
          timestamp: new Date()
        }];
      });
    } else if (mobilityAnalysisResult.type === 'error') {
      // Show error message and remove any pending "thinking" message
      setMessages(prev => {
        // Remove the last message if it's a "thinking" message
        const filtered = prev.filter((msg, idx) => {
          if (idx === prev.length - 1 && msg.isThinking) {
            return false;  // Remove thinking message
          }
          return true;
        });
        // Add the error message
        return [...filtered, {
          role: 'assistant',
          content: `❌ ${mobilityAnalysisResult.message}`,
          timestamp: new Date()
        }];
      });
    } else if (mobilityAnalysisResult.type === 'module_selection_prompt') {
      // Show "Pin Mode Activated - Select a module" message
      const promptMessage: ChatMessage = {
        role: 'assistant',
        content: mobilityAnalysisResult.message,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, promptMessage]);
    } else if (mobilityAnalysisResult.type === 'module_selected') {
      // Show module-specific prompt message
      const moduleMessage: ChatMessage = {
        role: 'assistant',
        content: mobilityAnalysisResult.message,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, moduleMessage]);
    } else if (mobilityAnalysisResult.type === 'pin_dropped') {
      // Show "Pin dropped, what would you like to know" message
      const pinDroppedMessage: ChatMessage = {
        role: 'assistant',
        content: mobilityAnalysisResult.message,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, pinDroppedMessage]);
    } else if (mobilityAnalysisResult.type === 'pending') {
      // Show "Analysis in progress..." message with robot thinking indicator
      const pendingMessage: ChatMessage = {
        role: 'assistant',
        content: mobilityAnalysisResult.message || '🤖 Analyzing...',
        timestamp: new Date(),
        isThinking: true  // Flag to show loading indicator with robot icon
      };
      setMessages(prev => [...prev, pendingMessage]);
    } else if (mobilityAnalysisResult.type === 'complete') {
      // Show geoint analysis results and remove any pending "thinking" message
      setMessages(prev => {
        // Remove the last message if it's a "thinking" message
        const filtered = prev.filter((msg, idx) => {
          if (idx === prev.length - 1 && msg.isThinking) {
            return false;  // Remove thinking/pending message
          }
          return true;
        });
        
        const result = mobilityAnalysisResult.data?.result;
        if (result) {
          let content = '';
          
          // Check if it's mobility analysis result
          if (result.summary) {
            content = result.summary;
          }
          // Check if it's terrain analysis result  
          else if (result.analysis) {
            content = `**Terrain Analysis:**\n\n${result.analysis}`;
            
            if (result.features_identified && result.features_identified.length > 0) {
              content += `\n\n**Features Identified:** ${result.features_identified.join(', ')}`;
            }
            
            if (result.imagery_metadata) {
              content += `\n\n**Imagery Source:** ${result.imagery_metadata.source || 'Unknown'}`;
              content += `\n**Date:** ${result.imagery_metadata.date || 'Unknown'}`;
            }
          }
          // Generic result
          else if (typeof result === 'string') {
            content = result;
          }
          
          if (content) {
            const resultMessage: ChatMessage = {
              role: 'assistant',
              content: content,
              timestamp: new Date()
            };
            return [...filtered, resultMessage];
          }
        }
        
        return filtered;
      });
    }
  }, [mobilityAnalysisResult]);

  const sendFeedback = (messageIndex: number, type: 'up' | 'down') => {
    setFeedback(prev => ({ ...prev, [messageIndex]: type }));
  };

  const chatMutation = useMutation({
    mutationFn: async (message: string) => {
      try {
        // Note: GEOINT analysis is now handled by MapView when a pin is dropped
        // Chat only handles normal conversational flow
        
        // Normal chat flow
        // Use working Enhanced PC Tools directly
        // This uses /chat endpoint which has the working satellite data search
        // Pass the conversation ID and message history for context
        console.log(`📍 Chat: Sending message with ${currentPin ? 'pin' : 'no pin'}:`, currentPin);
        console.log(`🎖️ Chat: GEOINT mode is ${geointMode ? 'ON' : 'OFF'}`);
        console.log(`🗺️ Chat: Including map context for vision capability:`, mapContext);
        const result = await apiService.sendChatMessage(message, selectedDataset?.id, conversationId, messages, currentPin || undefined, geointMode, mapContext);

        // Return the complete response object for map integration
        return result;
      } catch (error) {
        const err = error as any;
        if (err?.message?.includes('Failed to fetch') || err?.code === 'ECONNREFUSED') {
          throw new Error('Could not connect to backend. Please check your server and try again.');
        }
        throw error;
      }
    },
    onSuccess: (responseData) => {
      // Check if this is a GEOINT analysis result
      if (responseData?.geoint_result) {
        console.log('🧠 Chat: GEOINT analysis result received');
        const geointResult = responseData.geoint_result;
        
        // Format the response based on which agent was used
        let content = '';
        
        if (geointResult.intent) {
          content += `**Analysis Type:** ${geointResult.intent.agent.replace('_', ' ').toUpperCase()}\n`;
          content += `**Confidence:** ${(geointResult.intent.confidence * 100).toFixed(0)}%\n\n`;
        }
        
        const result = geointResult.result;
        
        // Mobility analysis result
        if (result?.summary) {
          content += result.summary;
        }
        // Terrain analysis result
        else if (result?.analysis) {
          content += result.analysis;
          
          if (result.features_identified && result.features_identified.length > 0) {
            content += `\n\n**Features Identified:** ${result.features_identified.join(', ')}`;
          }
          
          if (result.imagery_metadata) {
            content += `\n\n**Imagery Source:** ${result.imagery_metadata.source || 'Unknown'}`;
            content += `\n**Date:** ${result.imagery_metadata.date || 'Unknown'}`;
          }
        }
        // Building damage (future)
        else if (result?.message) {
          content += result.message;
        }
        
        setMessages(prev => ([
          ...prev,
          {
            role: 'assistant',
            content: content,
            timestamp: new Date()
          }
        ]));
        
        return;
      }
      
      // Normal chat response handling
      // responseData is normalized to workflow result when using /query or /enhanced-chat
      console.log('🚀🚀 CHAT.TSX onSuccess FIRED! 🚀🚀🚀');
      console.log('🔍 Chat: Complete responseData received:', responseData);
      console.log('🔍 Chat: responseData.response:', responseData?.response);
      console.log('🔍 Chat: responseData.user_response:', responseData?.user_response);
      console.log('🔍 Chat: responseData.message:', responseData?.message);

      // Try multiple fields for response content and extract text properly
      const rawResponse = responseData?.response || responseData?.user_response || responseData?.message || 'No response received';
      const textResponse = extractTextFromResponse(rawResponse);

      console.log('🔍 Chat: Raw response:', rawResponse);
      console.log('🔍 Chat: Extracted textResponse:', textResponse);
      console.log('🔍 Chat: textResponse length:', textResponse?.length);

      setMessages(prev => ([
        ...prev,
        {
          role: 'assistant',
          content: textResponse,
          timestamp: new Date()
        }
      ]));

      // Pass the complete response data to map for visualization
      console.log('🗺️ Chat: Passing response data to map:', JSON.stringify(responseData, null, 2));
      console.log('🗺️ Chat: Response data type:', typeof responseData);
      console.log('🗺️ Chat: Response data keys:', Object.keys(responseData || {}));

      // Pass the response data directly to the map without any hardcoded fallbacks
      const enhancedResponseData = responseData;

      if (onResponseReceived) {
        onResponseReceived(enhancedResponseData);
      }
    },
    onError: (error) => {
      setMessages(prev => ([
        ...prev,
        {
          role: 'assistant',
          content: error?.message || 'Sorry, I encountered an error. Please try again.',
          timestamp: new Date()
        }
      ]));
    }
  });

  // Private search mutation for VEDA AI Search (Direct Service)
  const privateSearchMutation = useMutation({
    mutationFn: async ({ query, collection_id }: { query: string; collection_id?: string }) => {
      try {
        console.log('🌍 Using direct VEDA search service:', { query, collection_id });
        const result = await vedaSearchService.search(query, collection_id);
        return result;
      } catch (error) {
        console.error('VEDA search error:', error);
        throw new Error('Failed to search VEDA datasets. Please check your configuration and try again.');
      }
    },
    onSuccess: (responseData) => {
      console.log('🔍 VEDA Search: Complete responseData received:', responseData);

      // Extract the answer from the VEDA AI Search response
      const textResponse = responseData?.answer || 'VEDA search completed successfully.';

      setMessages(prev => ([
        ...prev,
        {
          role: 'assistant',
          content: textResponse,
          timestamp: new Date(),
          source: 'veda_ai_search'
        }
      ]));

      // Pass the response data to map for visualization
      if (onResponseReceived) {
        onResponseReceived({
          message: textResponse,
          collections: responseData?.collections || [],
          source: 'veda_ai_search'
        });
      }
    },
    onError: (error) => {
      setMessages(prev => ([
        ...prev,
        {
          role: 'assistant',
          content: error?.message || 'Sorry, I encountered an error with the private search. Please try again.',
          timestamp: new Date()
        }
      ]));
    }
  });

  // Handle initial query from landing page
  useEffect(() => {
    if (initialQuery && chatMode && !initialQueryRef.current) {
      initialQueryRef.current = true;
      setInputValue(initialQuery);
      // Auto-send the initial query using main chat endpoint
      setTimeout(() => {
        const userMessage: ChatMessage = {
          role: 'user',
          content: initialQuery,
          timestamp: new Date()
        };
        setMessages(prev => [...prev, userMessage]);
        chatMutation.mutate(initialQuery);
        setInputValue('');
      }, 500); // Small delay to ensure chat mode is properly set
    }
  }, [initialQuery, chatMode]);

  // Handle private search triggers from sidebar (Updated to use main chat endpoint)
  useEffect(() => {
    if (privateSearchTrigger && privateSearchTrigger.isPrivateQuery) {
      console.log('🔍 Chat: Handling private search trigger:', privateSearchTrigger);
      
      const query = privateSearchTrigger.query;
      const collection_id = privateSearchTrigger.collection?.id;
      const collectionTitle = privateSearchTrigger.collection?.title || 'Dataset';
      
      // Clear previous chat and start fresh session
      const systemMessage: ChatMessage = {
        role: 'assistant',
        content: `🌍 **Earth Copilot Search Mode**\n\nI'll search for Earth Science data using our semantic translator and STAC catalog integration.\n\n**Query Context:** ${collectionTitle}\n\nLet me process your request...`,
        timestamp: new Date(),
        source: 'system'
      };
      
      const userMessage: ChatMessage = {
        role: 'user',
        content: query,
        timestamp: new Date()
      };
      
      // Reset chat with system message and user query
      setMessages([systemMessage, userMessage]);
      
      // Use main chat endpoint instead of VEDA search
      chatMutation.mutate(query);
    }
  }, [privateSearchTrigger]);

  const handleSendMessage = () => {
    if (!inputValue.trim()) return;

    // Add user message to chat BEFORE checking for interception
    const userMessage: ChatMessage = {
      role: 'user',
      content: inputValue,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);

    // Check if parent wants to intercept this message (e.g., for comparison query)
    if (onUserMessage && onUserMessage(inputValue)) {
      console.log('💬 Chat: Message intercepted by parent');
      setInputValue('');
      return;
    }
    
    // Use main chat endpoint instead of VEDA search (VEDA integration disabled)
    console.log('🔍 Chat: Sending message via main chat endpoint:', { inputValue, selectedDataset: selectedDataset?.id });
    chatMutation.mutate(inputValue);
    
    setInputValue('');
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleExampleClick = (example: string) => {
    setInputValue(example);
  };

  useEffect(() => {
    // Only auto-scroll to bottom if user is already near the bottom
    const messagesContainer = messagesEndRef.current?.parentElement;
    if (messagesContainer) {
      const { scrollTop, scrollHeight, clientHeight } = messagesContainer;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;

      if (isNearBottom || messages.length <= 1) {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      }
    }
  }, [messages]);

  const getPlanetaryComputerExamples = (dataset: Dataset | null): string[] => {
    const defaultExamples = [
      'Show Sentinel-2 images of Seattle from last month',
      'Find Landsat imagery of the Amazon with <10% cloud cover',
      'Satellite data for Washington DC from June 2024'
    ];

    if (!dataset) return defaultExamples;

    const pcExamples: Record<string, string[]> = {
      'landsat-c2-l2': [
        'Find Landsat imagery of the Amazon with <10% cloud cover',
        'Show agricultural changes in Iowa from 2020 to 2024',
        'Analyze deforestation in Brazil using Landsat data',
        'Find cloud-free Landsat scenes over New York City'
      ],
      'sentinel-2-l2a': [
        'Show Sentinel-2 images of Seattle from last month',
        'Find Sentinel-2 data for crop monitoring in France',
        'Analyze forest health using Sentinel-2 NDVI',
        'Show coastal erosion patterns using Sentinel-2'
      ],
      'sentinel-1-rtc': [
        'Detect ships in the Mediterranean Sea using SAR data',
        'Show flood mapping using Sentinel-1 radar data',
        'Analyze soil moisture patterns in agricultural regions',
        'Find oil spills using SAR imagery'
      ],
      'modis': [
        'Show global fire hotspots from MODIS data',
        'Track sea surface temperatures in the Pacific',
        'Analyze vegetation phenology using MODIS time series',
        'Show aerosol optical depth during dust storms'
      ],
      'daymet-daily-na': [
        'What was the precipitation in Montana last month?',
        'Show temperature trends for the Great Lakes region',
        'Find the wettest day in California in 2023',
        'Compare growing degree days across different states'
      ],
      'era5-pds': [
        'Show wind patterns during Hurricane Ian',
        'What were the temperature anomalies in Europe in 2023?',
        'Analyze precipitation patterns during El Niño',
        'Show atmospheric pressure changes during storms'
      ],
      'nasadem': [
        'Show elevation profile for the Rocky Mountains',
        'Find the highest peaks in the Himalayas',
        'Calculate slope and aspect for watershed analysis',
        'Show topographic relief for flood risk assessment'
      ],
      'goes-cmi': [
        'Show cloud patterns over the Atlantic hurricane region',
        'Track storm development in real-time imagery',
        'Analyze fire hotspots from GOES satellite data',
        'Show fog patterns affecting airport operations'
      ],
      'terraclimate': [
        'Show drought conditions in the southwestern US',
        'Analyze long-term precipitation trends in Africa',
        'Find the driest years in Australia since 1958',
        'Compare water balance across different climate zones'
      ],
      'gbif': [
        'Where have polar bears been spotted recently?',
        'Show bird migration patterns in North America',
        'Find endangered species observations in Madagascar',
        'Analyze biodiversity hotspots using GBIF data'
      ],
      'aster-l1t': [
        'Show mineral composition analysis of copper mines',
        'Analyze volcanic thermal signatures using ASTER',
        'Find lithological mapping for geological surveys',
        'Show urban heat island effects using thermal bands'
      ],
      'cop-dem-glo-30': [
        'Calculate watershed boundaries for river basins',
        'Show terrain analysis for infrastructure planning',
        'Find optimal locations for renewable energy projects',
        'Analyze landslide susceptibility using slope data'
      ]
    };

    return pcExamples[dataset.id] || [
      `Analyze ${dataset.title} data for environmental monitoring`,
      `Show recent ${dataset.title} data for a specific region`,
      `What insights can I get from ${dataset.title}?`,
      `How do I query ${dataset.title} using specific parameters?`
    ];
  };

  const examples: string[] = getPlanetaryComputerExamples(selectedDataset);

  return (
    <div className="right">
      <div className="chat chat-container">
        <div className="header">
          <span style={{ fontSize: '22px' }}>🤖</span>
          <span>GeoCopilot</span>
        </div>

        <div className="messages">
          {/* Examples removed to prevent flash on page load */}

          {messages.map((message, index) => (
            <div key={index} className={`row ${message.role}`}>
              <div className="message-wrapper">
                {message.isThinking ? (
                  <div className="msg">
                    <div className="loading-indicator">
                      <span>🤖</span>
                      <span>Thinking...</span>
                    </div>
                  </div>
                ) : (
                  <div className="msg" dangerouslySetInnerHTML={{
                    __html: renderMessageHTML(message.content)
                  }}></div>
                )}
                {message.role === 'assistant' && !message.isThinking && (
                  <div className="reactions">
                    <button
                      className="icon-btn"
                      title="Thumbs up"
                      onClick={() => sendFeedback(index, 'up')}
                      aria-label="Thumbs up"
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                        <path d="M2 10h4v12H2V10zm20 2c0-1.1-.9-2-2-2h-6.31l.95-4.57.03-.32c0-.41-.17-.79-.44-1.06L13 2 7.59 7.41C7.22 7.78 7 8.3 7 8.83V20c0 1.1.9 2 2 2h7c.82 0 1.54-.5 1.84-1.22l3.02-7.05c.09-.23.14-.47.14-.73v-1z" />
                      </svg>
                    </button>
                    <button
                      className="icon-btn"
                      title="Thumbs down"
                      onClick={() => sendFeedback(index, 'down')}
                      aria-label="Thumbs down"
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                        <path d="M22 14h-4V2h4v12zM2 12c0 1.1.9 2 2 2h6.31l-.95 4.57-.03.32c0 .41.17.79.44 1.06L11 22l5.41-5.41c.37-.37.59-.89.59-1.42V4c0-1.1-.9-2-2-2H8c-.82 0-1.54.5-1.84 1.22L3.14 10.27c-.09.23-.14.47-.14.73v1z" />
                      </svg>
                    </button>
                    {feedback[index] && (
                      <span className="desc" style={{ marginLeft: 6 }}>
                        {feedback[index] === 'up' ? "Thanks for the feedback." : "We'll improve this."}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          {chatMutation.isPending && (
            <div className="row assistant">
              <div>
                <div className="msg">
                  <div className="loading-indicator">
                    <span>🤖</span>
                    <span>Thinking...</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="footer">
          <div className="footer-content">
            <textarea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder={
                geointMode
                  ? "📍 Drop a pin on the map for mobility analysis..."
                  : isVedaMode 
                  ? "Ask about climate data, earth observations, or environmental datasets..."
                  : selectedDataset
                  ? `Ask about ${selectedDataset.title}...`
                  : "Ask about Earth data..."
              }
              disabled={chatMutation.isPending}
            />
            <button
              className={`btn send ${inputValue.trim() ? 'has-text' : ''}`}
              onClick={handleSendMessage}
              disabled={!inputValue.trim() || chatMutation.isPending}
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Chat;
