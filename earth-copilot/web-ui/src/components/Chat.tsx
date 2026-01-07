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
  
  // Convert markdown headers (##, ###, ####) to styled headers
  s = s.replace(/^#{2,4}\s+(.+)$/gm, '<strong style="font-size: 1.1em; display: block; margin-top: 16px; margin-bottom: 8px; color: #1e3a8a;">$1</strong>');
  
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
  terrainSession?: { sessionId: string | null; lat: number; lng: number } | null; // Terrain session for multi-turn chat
  onClearTerrainSession?: () => void; // Callback to clear terrain session
  visionSession?: { sessionId: string | null; lat: number; lng: number } | null; // Vision session for multi-turn chat
  onClearVisionSession?: () => void; // Callback to clear vision session
  onComparisonResult?: (result: any) => void; // Callback for comparison analysis results (before/after data)
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
  terrainSession,
  onClearTerrainSession,
  visionSession,
  onClearVisionSession,
  onComparisonResult,
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
  
  // 👁️ Local vision session ID tracking (for first message -> follow-ups)
  const [localVisionSessionId, setLocalVisionSessionId] = useState<string | null>(null);
  
  // VEDA search mode state
  const [isVedaMode, setIsVedaMode] = useState(false);
  const [currentCollectionId, setCurrentCollectionId] = useState<string | null>(null);
  
  // State for pending query from GetStartedButton
  const [pendingQuery, setPendingQuery] = useState<string | null>(null);

  // Add welcome message when chat component first mounts
  useEffect(() => {
    if (messages.length === 0 && !selectedDataset) {
      const welcomeMessage: ChatMessage = {
        role: 'assistant',
        content: "Welcome to Earth Copilot! I'm here to help you find datasets that include location and date details. Whether you're tracking time-sensitive trends or exploring geospatial insights, I've got you covered. Just tell me what you're working on, and we'll get started!",
        timestamp: new Date()
      };
      setMessages([welcomeMessage]);
    }
  }, []); // Run only once on mount

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
  
  // 👁️ Clear local vision session when vision mode is deactivated
  useEffect(() => {
    if (selectedModule !== 'vision' && localVisionSessionId) {
      console.log('👁️ Chat: Vision mode deactivated, clearing local session');
      setLocalVisionSessionId(null);
    }
  }, [selectedModule, localVisionSessionId]);
  
  // Listen for query events from GetStartedButton
  useEffect(() => {
    const handleQueryEvent = (event: CustomEvent<{ query: string }>) => {
      const query = event.detail.query;
      if (query && query.trim()) {
        console.log('📝 Chat: Received query from GetStartedButton:', query);
        // Set the pending query to trigger processing after chatMutation is ready
        setPendingQuery(query);
      }
    };

    window.addEventListener('earthcopilot-query' as any, handleQueryEvent as any);
    return () => {
      window.removeEventListener('earthcopilot-query' as any, handleQueryEvent as any);
    };
  }, []); // Empty dependencies - listener persists
  
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
    } else if (mobilityAnalysisResult.type === 'cancel_thinking') {
      // Remove all pending "thinking" messages without adding new content
      // Used when user repositions terrain pin to cancel previous analysis
      console.log('🗑️ Chat: Cancelling pending thinking messages');
      setMessages(prev => prev.filter(msg => !msg.isThinking));
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
        // 👁️ VISION CHAT ROUTING
        // Route to vision agent if:
        // 1. We have an explicit vision session with sessionId, OR
        // 2. We have a local vision session (from first call), OR
        // 3. Vision mode is active via mapContext (user dropped pin while vision module selected)
        const hasVisionSession = visionSession && visionSession.sessionId;
        const hasLocalVisionSession = !!localVisionSessionId;
        const hasVisionContext = selectedModule === 'vision' && mapContext?.vision_mode && mapContext?.vision_pin;
        
        if (hasVisionSession || hasLocalVisionSession || hasVisionContext) {
          // Use session coordinates or mapContext coordinates
          const lat = visionSession?.lat ?? mapContext?.vision_pin?.lat ?? 0;
          const lng = visionSession?.lng ?? mapContext?.vision_pin?.lng ?? 0;
          // Prefer local session ID (from previous call) over prop session ID
          const sessionId = localVisionSessionId ?? visionSession?.sessionId ?? null;
          
          console.log('👁️ Chat: Routing to vision agent', {
            hasVisionSession,
            hasLocalVisionSession,
            hasVisionContext,
            sessionId,
            lat,
            lng,
            hasScreenshot: !!mapContext?.imagery_base64,
            hasTileUrls: !!(mapContext?.tile_urls?.length),
            collection: mapContext?.current_collection
          });
          
          const { sendVisionChatMessage } = await import('../services/api');
          const result = await sendVisionChatMessage(
            sessionId,
            message,
            lat,
            lng,
            mapContext?.imagery_base64, // Include screenshot for vision analysis
            mapContext  // Pass full map context with tile_urls, collection, bounds
          );
          
          console.log('👁️ Chat: Vision agent response:', result);
          console.log('🔧 Chat: Tool calls:', result.tool_calls);
          
          // 👁️ Store session ID for follow-up questions
          if (result.session_id && !localVisionSessionId) {
            console.log('👁️ Chat: Storing vision session ID for follow-ups:', result.session_id);
            setLocalVisionSessionId(result.session_id);
          }
          
          // Check if agent wants to exit vision mode
          const exitAction = result.tool_calls?.find((tc: any) => {
            if (tc.tool === 'exit_analysis_mode') {
              console.log('🚪 Found exit_analysis_mode tool call:', tc);
              return true;
            }
            if (tc.result?.action === 'EXIT_GEOINT_MODE') {
              console.log('🚪 Found EXIT_GEOINT_MODE action:', tc);
              return true;
            }
            if (typeof tc.result === 'string' && tc.result.includes('EXIT_GEOINT_MODE')) {
              console.log('🚪 Found EXIT_GEOINT_MODE in string result:', tc);
              return true;
            }
            return false;
          });
          
          if (exitAction) {
            console.log('🚪 Chat: Vision agent requested exit - routing to main chat');
            
            // Clear vision session (both local and prop-based)
            setLocalVisionSessionId(null);
            if (onClearVisionSession) {
              onClearVisionSession();
            }
            
            // Get the query to reprocess (original user message or from tool result)
            let queryToReprocess = message;
            if (exitAction.result?.reprocess_query) {
              queryToReprocess = exitAction.result.reprocess_query;
            } else if (typeof exitAction.result === 'string') {
              try {
                const parsed = JSON.parse(exitAction.result);
                if (parsed.reprocess_query) {
                  queryToReprocess = parsed.reprocess_query;
                }
              } catch (e) {
                // Use original message
              }
            }
            
            // Reprocess query through main chat
            console.log('🔄 Chat: Reprocessing query through main chat:', queryToReprocess);
            const { sendMessage } = await import('../services/api');
            const mainResult = await sendMessage(queryToReprocess, selectedDataset || undefined);
            return mainResult.reply;
          }
          
          return result.response || result.content;
        }
        
        // 🌍 TERRAIN CHAT ROUTING
        // If we have an active terrain session, route messages to terrain agent
        if (terrainSession && terrainSession.sessionId) {
          console.log('🌍 Chat: Routing to terrain agent (session:', terrainSession.sessionId, ')');
          console.log('📸 Chat: Including screenshot for terrain agent:', !!mapContext?.imagery_base64);
          
          const { sendTerrainChatMessage } = await import('../services/api');
          const result = await sendTerrainChatMessage(
            terrainSession.sessionId,
            message,
            terrainSession.lat,
            terrainSession.lng,
            mapContext?.imagery_base64, // Include screenshot for vision analysis
            5.0
          );
          
          console.log('🌍 Chat: Terrain agent response:', result);
          console.log('🔧 Chat: Tool calls:', result.tool_calls);
          
          // Check if agent wants to exit terrain mode
          // The exit_analysis_mode tool returns an action in tool_calls
          // The result might be a string (JSON) or an object
          const exitAction = result.tool_calls?.find((tc: any) => {
            if (tc.tool === 'exit_analysis_mode') {
              console.log('🚪 Found exit_analysis_mode tool call:', tc);
              return true;
            }
            // Handle case where result is a parsed object
            if (tc.result?.action === 'EXIT_GEOINT_MODE') {
              console.log('🚪 Found EXIT_GEOINT_MODE action:', tc);
              return true;
            }
            // Handle case where result is a string containing the action
            if (typeof tc.result === 'string' && tc.result.includes('EXIT_GEOINT_MODE')) {
              console.log('🚪 Found EXIT_GEOINT_MODE in string result:', tc);
              return true;
            }
            return false;
          });
          
          if (exitAction) {
            console.log('🚪 Chat: Terrain agent requested exit - routing to main chat');
            
            // Clear terrain session
            if (onClearTerrainSession) {
              onClearTerrainSession();
            }
            
            // Get the query to reprocess (original user message or from tool result)
            let queryToReprocess = message;
            if (exitAction.result?.reprocess_query) {
              queryToReprocess = exitAction.result.reprocess_query;
            } else if (typeof exitAction.result === 'string') {
              // Try to parse JSON string result
              try {
                const parsed = JSON.parse(exitAction.result);
                if (parsed.reprocess_query) {
                  queryToReprocess = parsed.reprocess_query;
                }
              } catch (e) {
                // Use original message
              }
            }
            
            console.log('🚪 Chat: Reprocessing query:', queryToReprocess);
            
            // Route to main chat with geointMode=false to ensure it's handled as a regular query
            // (not routed back to terrain analysis)
            const mainResult = await apiService.sendChatMessage(
              queryToReprocess, 
              selectedDataset?.id, 
              conversationId, 
              messages, 
              currentPin || undefined, 
              false,  // Explicitly false - we just exited terrain mode
              mapContext
            );
            
            console.log('🚪 Chat: Main chat result after exit:', mainResult);
            return mainResult;
          }
          
          // Return terrain agent result (will be handled by onSuccess)
          return {
            response: result.response,
            session_id: result.session_id,
            tool_calls: result.tool_calls,
            isTerrainResponse: true
          };
        }
        
        // 📊 COMPARISON ROUTING
        // Route to comparison agent when comparison module is selected
        if (selectedModule === 'comparison') {
          console.log('📊 Chat: Routing to comparison agent');
          console.log('📊 Chat: Query:', message);
          console.log('📊 Chat: Map context:', {
            lat: mapContext?.vision_pin?.lat || currentPin?.lat,
            lng: mapContext?.vision_pin?.lng || currentPin?.lng
          });
          
          try {
            const response = await apiService.triggerGeointAnalysis(
              'comparison',
              mapContext?.vision_pin?.lat || currentPin?.lat || 0,
              mapContext?.vision_pin?.lng || currentPin?.lng || 0,
              message, // user_query
              undefined, // userContext
              undefined, // screenshot
              undefined  // signal
            );
            
            console.log('📊 Chat: Comparison agent response:', response);
            
            // Handle prompt responses (agent asking for clarification)
            if (response.type === 'prompt') {
              return {
                response: response.message,
                isComparisonResponse: true,
                isPrompt: true
              };
            }
            
            // Handle comparison results
            if (response.type === 'comparison' && response.result) {
              const result = response.result;
              
              // Build response message
              let content = '**📊 Temporal Comparison Analysis**\n\n';
              
              if (result.location_name) {
                content += `📍 **Location:** ${result.location_name}\n`;
              }
              
              if (result.before_date && result.after_date) {
                content += `📅 **Time Period:** ${result.before_date} → ${result.after_date}\n\n`;
              }
              
              if (result.analysis) {
                content += result.analysis;
              } else if (result.summary) {
                content += result.summary;
              }
              
              return {
                response: content,
                isComparisonResponse: true,
                comparisonData: result // Pass for map rendering (before/after toggle)
              };
            }
            
            // Fallback
            return {
              response: response.message || 'Comparison analysis complete.',
              isComparisonResponse: true
            };
            
          } catch (error: any) {
            console.error('📊 Chat: Comparison agent error:', error);
            return {
              response: `❌ Comparison analysis failed: ${error.message}`,
              isComparisonResponse: true,
              isError: true
            };
          }
        }
        
        // Note: GEOINT analysis is now handled by MapView when a pin is dropped
        // Chat only handles normal conversational flow
        
        // Normal chat flow
        // Use working Enhanced PC Tools directly
        // This uses /chat endpoint which has the working satellite data search
        // Pass the conversation ID and message history for context
        console.log(`📍 Chat: Sending message with ${currentPin ? 'pin' : 'no pin'}:`, currentPin);
        console.log(`🎖️ Chat: GEOINT mode is ${geointMode ? 'ON' : 'OFF'}`);
        console.log(`🗺️ Chat: Map context for vision:`, {
          has_satellite_data: mapContext?.has_satellite_data,
          has_screenshot: !!mapContext?.imagery_base64,
          collection: mapContext?.current_collection,
          tile_urls_count: mapContext?.tile_urls?.length || 0,
          vision_mode: mapContext?.vision_mode,
          vision_pin: mapContext?.vision_pin
        });
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
      
      // 📊 COMPARISON RESPONSE HANDLING
      if (responseData?.isComparisonResponse) {
        console.log('📊 Chat: Comparison analysis result received');
        
        setMessages(prev => ([
          ...prev,
          {
            role: 'assistant',
            content: responseData.response,
            timestamp: new Date()
          }
        ]));
        
        // If we have comparison data, notify parent to render before/after toggle
        if (responseData.comparisonData && onComparisonResult) {
          onComparisonResult(responseData.comparisonData);
        }
        
        return;
      }
      
      // Normal chat response handling
      // responseData is normalized to workflow result when using /query or /enhanced-chat
      console.log('🚀🚀 CHAT.TSX onSuccess FIRED! 🚀🚀🚀');
      console.log('🔍 Chat: Complete responseData received:', responseData);
      console.log('🔍 Chat: responseData type:', typeof responseData);
      console.log('🔍 Chat: responseData.response:', responseData?.response);
      console.log('🔍 Chat: responseData.user_response:', responseData?.user_response);
      console.log('🔍 Chat: responseData.message:', responseData?.message);

      // Handle case where responseData is already a string (e.g., from vision agent)
      let rawResponse: string;
      if (typeof responseData === 'string') {
        rawResponse = responseData;
        console.log('🔍 Chat: responseData is string, using directly');
      } else {
        // Try multiple fields for response content
        rawResponse = responseData?.response || responseData?.user_response || responseData?.message || 'No response received';
        console.log('🔍 Chat: Extracted rawResponse from object properties');
      }
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

  // Handle pending query from GetStartedButton
  useEffect(() => {
    if (pendingQuery && pendingQuery.trim()) {
      console.log('✅ Chat: Processing pending query:', pendingQuery);
      
      // Set the input value
      setInputValue(pendingQuery);
      
      // Add user message
      const userMessage: ChatMessage = {
        role: 'user',
        content: pendingQuery,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, userMessage]);
      
      // Send the message using the chat mutation
      chatMutation.mutate(pendingQuery);
      
      // Clear the pending query and input
      setPendingQuery(null);
      setInputValue('');
    }
  }, [pendingQuery, chatMutation]);

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
    } else if (privateSearchTrigger && privateSearchTrigger.isPCStructuredSearch) {
      console.log('🔧 Chat: Handling PC structured search trigger:', privateSearchTrigger);
      
      const params = privateSearchTrigger.pcSearchParams;
      
      // Create display message
      let displayQuery = `Searching ${params.collection} for ${params.location}`;
      if (params.datetime) {
        displayQuery += ` on ${params.datetime}`;
      } else if (params.datetime_start && params.datetime_end) {
        displayQuery += ` from ${params.datetime_start} to ${params.datetime_end}`;
      }
      
      const userMessage: ChatMessage = {
        role: 'user',
        content: displayQuery,
        timestamp: new Date()
      };
      
      setMessages(prev => [...prev, userMessage]);
      
      // Add thinking indicator
      const thinkingMessage: ChatMessage = {
        role: 'assistant',
        content: '🤖 Searching Planetary Computer...',
        timestamp: new Date(),
        isThinking: true
      };
      
      setMessages(prev => [...prev, thinkingMessage]);
      
      // Call structured search endpoint
      const handleStructuredSearch = async () => {
        try {
          const result = await apiService.structuredSearch(params);
          
          // Remove thinking message and add assistant response
          setMessages(prev => {
            const filtered = prev.filter((msg, idx) => {
              if (idx === prev.length - 1 && msg.isThinking) {
                return false; // Remove thinking message
              }
              return true;
            });
            
            const assistantMessage: ChatMessage = {
              role: 'assistant',
              content: result.response || result.user_response || 'Search completed.',
              timestamp: new Date()
            };
            
            return [...filtered, assistantMessage];
          });
          
          // Pass to map for visualization (same as chatMutation.onSuccess)
          if (onResponseReceived && result.success) {
            onResponseReceived(result);
          }
          
        } catch (error) {
          console.error('Structured search error:', error);
          
          // Remove thinking message and add error message
          setMessages(prev => {
            const filtered = prev.filter((msg, idx) => {
              if (idx === prev.length - 1 && msg.isThinking) {
                return false; // Remove thinking message
              }
              return true;
            });
            
            const errorMessage: ChatMessage = {
              role: 'assistant',
              content: 'Sorry, the structured search failed. Please try again.',
              timestamp: new Date()
            };
            
            return [...filtered, errorMessage];
          });
        }
      };
      
      handleStructuredSearch();
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
    // Always auto-scroll to bottom to show the latest message
    // This ensures users always see the most recent chat response
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
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
                visionSession && visionSession.sessionId
                  ? "Ask a follow-up question about this imagery..."
                  : terrainSession && terrainSession.sessionId
                  ? "Ask a follow-up question about this terrain..."
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
// Build trigger: 2026-01-06 15:04:47
