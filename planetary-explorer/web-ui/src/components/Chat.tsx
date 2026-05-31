// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState, useRef, useEffect } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { apiService, Dataset, ChatMessage, MapContext } from '../services/api';
import { enhanceMessageForMapVisualization, hasVisualizableData } from './PlanetaryExplorerMapIntegration';
import vedaSearchService from '../services/vedaSearchService';
import SourceChips from './SourceChips';
import { TraceDrawer, ConfirmationCard, useToolTrace } from './trace';
import type { PendingConfirm } from './trace';

// Enhanced function to extract text from complex response objects
function extractTextFromResponse(content: any): string {
  console.log(' extractTextFromResponse: Input type:', typeof content);
  console.log(' extractTextFromResponse: Input content preview:', String(content).substring(0, 150) + '...');

  if (typeof content === 'string') {
    const contentStr = content;

    // Check if it's a ChatMessageContent object by looking for the specific pattern
    if (contentStr.includes('ChatMessageContent(') && contentStr.includes('ChatCompletionMessage(content=')) {
      console.log(' extractTextFromResponse: Detected ChatMessageContent string format');
      console.log(' extractTextFromResponse: String starts with:', contentStr.substring(0, 200));
      console.log(' extractTextFromResponse: Looking for ChatCompletionMessage pattern...');

      // Use a very specific regex for the exact pattern we're seeing
      // This matches: ChatCompletionMessage(content='...content...'
      const messageContentMatch = contentStr.match(/ChatCompletionMessage\(content='([^']*(?:\\'[^']*)*?)'/s);
      if (messageContentMatch && messageContentMatch[1]) {
        console.log(' extractTextFromResponse:  Successfully extracted from ChatCompletionMessage');
        console.log(' extractTextFromResponse: Extracted length:', messageContentMatch[1].length);
        let extracted = messageContentMatch[1];
        // Convert escaped characters back to normal
        extracted = extracted.replace(/\\n/g, '\n');
        extracted = extracted.replace(/\\'/g, "'");
        extracted = extracted.replace(/\\\\/g, '\\');
        return extracted;
      } else {
        console.log(' extractTextFromResponse:  ChatCompletionMessage regex did not match');
      }

      // Alternative: try to find content=' pattern anywhere in the string
      const generalContentMatch = contentStr.match(/content='([^']*(?:\\'[^']*)*?)'/s);
      if (generalContentMatch && generalContentMatch[1] && generalContentMatch[1].length > 100) {
        console.log(' extractTextFromResponse:  Found content using general pattern');
        console.log(' extractTextFromResponse: Extracted length:', generalContentMatch[1].length);
        let extracted = generalContentMatch[1];
        extracted = extracted.replace(/\\n/g, '\n');
        extracted = extracted.replace(/\\'/g, "'");
        extracted = extracted.replace(/\\\\/g, '\\');
        return extracted;
      } else {
        console.log(' extractTextFromResponse:  General content pattern did not match or too short');
      }

      console.log(' extractTextFromResponse:  Could not extract content with regex patterns');
    } else {
      console.log(' extractTextFromResponse: Not a ChatMessageContent format, treating as regular string');
    }

    // If it's just a regular string, return as-is
    return content;
  }

  if (Array.isArray(content)) {
    console.log(' extractTextFromResponse: Processing array with', content.length, 'items');
    return content.map(item => extractTextFromResponse(item)).join('');
  }

  if (typeof content === 'object' && content !== null) {
    // Handle direct object access if the object has proper structure
    try {
      // Check if we can access properties directly (for proper object instances)
      if (content.items && Array.isArray(content.items)) {
        console.log(' extractTextFromResponse: Processing items array directly');
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
      console.log(' extractTextFromResponse: Object property access failed, trying string conversion');
    }

    // Convert object to string and try regex extraction
    const contentStr = String(content);
    if (contentStr.includes('content=')) {
      const match = contentStr.match(/content='([^']*(?:\\'[^']*)*?)'/s);
      if (match && match[1] && match[1].length > 50) {
        console.log(' extractTextFromResponse:  Extracted from object string conversion');
        let extracted = match[1];
        extracted = extracted.replace(/\\n/g, '\n');
        extracted = extracted.replace(/\\'/g, "'");
        return extracted;
      }
    }
  }

  console.log(' extractTextFromResponse:  Fallback to string conversion');
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

  // Normalize CRLF and collapse 3+ blank lines so we don't end up with a
  // wall of <br/> separators between sections.
  s = s.replace(/\r\n/g, '\n').replace(/\n{3,}/g, '\n\n');

  // --- Block-level transforms (must run before inline) ---
  // Each block transform emits an HTML element that includes its own
  // vertical spacing. The trailing `\n` after that element is scrubbed
  // below so it doesn't get an extra `<br/>` injected.
  const H = 'font-size:1.05em;font-weight:600;color:#1e3a8a;display:block;margin:14px 0 6px;';
  const LI = (ml: number) => `display:block;margin:2px 0 2px ${ml}px;padding-left:14px;text-indent:-14px;line-height:1.45;`;
  const MARK = 'display:inline-block;width:14px;color:#475569;font-weight:600;';

  // Numbered section headers like "1) Overview" — kept for back-compat.
  s = s.replace(/^(\d+\))\s+(.+)$/gm,
    `<div style="${H}">$1 $2</div>`);

  // Markdown headers (#, ##, ###, ####) -> styled section headers.
  s = s.replace(/^#{1,4}\s+(.+)$/gm, `<div style="${H}">$1</div>`);

  // Numbered list items: "1. text" / "2. text". Treat as ordered bullets.
  s = s.replace(/^(\s*)(\d+)\.\s+(.+)$/gm, (_m, indent: string, n: string, body: string) => {
    const depth = Math.floor((indent || '').length / 2);
    const ml = 16 + depth * 18;
    return `<div style="${LI(ml)}"><span style="${MARK}">${n}.</span>${body}</div>`;
  });

  // Bulleted list items: "- text", "* text", "• text". Honor 2-space indent
  // for nesting so the model's "header bullet -> sub-bullet" structure is
  // preserved instead of being flattened.
  s = s.replace(/^(\s*)[-*•]\s+(.+)$/gm, (_m, indent: string, body: string) => {
    const depth = Math.floor((indent || '').length / 2);
    const ml = 16 + depth * 18;
    return `<div style="${LI(ml)}"><span style="${MARK}">•</span>${body}</div>`;
  });

  // --- Inline transforms ---
  // Bold **text** -> <strong>. Italics _text_ -> <em>. We deliberately
  // do NOT translate single-`*` runs to <em> because the LLM uses `*` for
  // multiplication and footnotes (e.g. "(B05 - B04) / (B05 + B04)") and
  // mis-italicizing them produces garbage.
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/(^|[\s(])_([^_\n]+)_(?=[\s).,;:!?]|$)/g, '$1<em>$2</em>');

  // Inline code `foo` -> styled span.
  s = s.replace(/`([^`\n]+)`/g, '<code style="background:rgba(148,163,184,0.18);padding:1px 5px;border-radius:3px;font-size:0.92em;">$1</code>');

  // --- Final line-break pass ---
  // Convert remaining single newlines to `<br/>` for inline flow, but
  // strip the `<br/>` immediately after a block element we emitted so
  // headers/bullets don't get an extra blank line under them.
  s = s.replace(/\n/g, '<br/>');
  s = s.replace(/(<\/div>)(<br\/>)+/g, '$1');
  // Collapse `<br/><br/>` runs of 3+ to 2 (one visible blank line max).
  s = s.replace(/(<br\/>){3,}/g, '<br/><br/>');
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
  mobilityPinCoords?: { pinA: { lat: number; lng: number }; pinB: { lat: number; lng: number } } | null; // Pin A/B coordinates for mobility
  selectedModule?: string; // Selected GEOINT module (terrain_analysis, mobility_analysis, building_damage)
  mapContext?: MapContext; // Map context for Chat Vision capability
  systemMessage?: string | null; // System messages from workflow
  onUserMessage?: (message: string) => boolean; // Callback when user sends message, returns true if intercepted
  terrainSession?: { sessionId: string | null; lat: number; lng: number } | null; // Terrain session for multi-turn chat
  onTerrainSessionChange?: (session: { sessionId: string | null; lat: number; lng: number } | null) => void; // Update terrain session (e.g. after first response creates session)
  onClearTerrainSession?: () => void; // Callback to clear terrain session
  visionSession?: { sessionId: string | null; lat: number; lng: number } | null; // Vision session for multi-turn chat
  onClearVisionSession?: () => void; // Callback to clear vision session
  onComparisonResult?: (result: any) => void; // Callback for comparison analysis results (before/after data)
  selectedModel?: string; // Selected AI model (gpt-5)
  stacMode?: 'public' | 'pro'; // Public MPC vs MPC Pro (private GeoCatalog) for STAC routing
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
  mobilityPinCoords,
  selectedModule,
  mapContext,
  systemMessage,
  onUserMessage,
  terrainSession,
  onTerrainSessionChange,
  onClearTerrainSession,
  visionSession,
  onClearVisionSession,
  onComparisonResult,
  selectedModel,
  stacMode,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [feedback, setFeedback] = useState<Record<number, string>>({});
  // MCP tool-trace state for the active streaming turn. Rows are
  // captured here and copied onto the resilient ChatMessage after the
  // stream resolves so the drawer renders beneath the message bubble.
  const activeTrace = useToolTrace();
  // Pending WRITE/DESTRUCTIVE confirmations awaiting Approve/Deny. Keyed
  // by trace_id so duplicate `confirm_request` events coalesce.
  const [pendingConfirms, setPendingConfirms] = useState<PendingConfirm[]>([]);
  const handleConfirmResolved = React.useCallback(
    (traceId: string, _approved: boolean) => {
      setPendingConfirms((prev) => prev.filter((p) => p.traceId !== traceId));
    },
    [],
  );
  const messagesEndRef = useRef<HTMLDivElement>(null);
  // Tracks whether the user clicked Stop on the current in-flight chat turn.
  // We can't cancel the in-flight HTTP request through TanStack mutations
  // here without threading an AbortSignal through every fetch in the
  // mutationFn, but we CAN ignore the eventual onSuccess/onError result
  // and clear the "Thinking..." UI immediately so the chat feels responsive.
  const cancelledRef = useRef<boolean>(false);
  // AbortController for the in-flight /api/query call. Stop sets cancelledRef
  // AND calls abort() so the HTTP request is genuinely terminated end-to-end
  // (axios honors the signal and the backend connection drops).
  const chatAbortRef = useRef<AbortController | null>(null);
  const [hasProcessedInitialQuery, setHasProcessedInitialQuery] = useState(false);
  const initialQueryRef = useRef(false);
  const [lastResponse, setLastResponse] = useState<string>('');
  // Add conversation ID to maintain context across messages
  const [conversationId] = useState(() => `web-session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`);
  
  //  Local vision session ID tracking (for first message -> follow-ups)
  const [localVisionSessionId, setLocalVisionSessionId] = useState<string | null>(null);
  
  // VEDA search mode state
  const [isVedaMode, setIsVedaMode] = useState(false);
  const [currentCollectionId, setCurrentCollectionId] = useState<string | null>(null);
  
  // State for pending query from GetStartedButton
  const [pendingQuery, setPendingQuery] = useState<string | null>(null);
  
  // State for analysis type hint (raster vs screenshot) from GetStartedButton
  const [pendingAnalysisType, setPendingAnalysisType] = useState<'raster' | 'screenshot' | null>(null);
  
  // Refs to track latest prop values (avoid stale closures in event listeners)
  const selectedModuleRef = useRef(selectedModule);
  const mapContextRef = useRef(mapContext);
  const terrainSessionRef = useRef(terrainSession);
  
  // Keep refs updated with latest prop values
  useEffect(() => {
    selectedModuleRef.current = selectedModule;
    mapContextRef.current = mapContext;
    terrainSessionRef.current = terrainSession;
  }, [selectedModule, mapContext, terrainSession]);

  // Add welcome message when chat component first mounts.
  // Source-of-truth: this is the only place the opener is rendered.
  useEffect(() => {
    if (messages.length === 0 && !selectedDataset) {
      const welcomeMessage: ChatMessage = {
        role: 'assistant',
        content: "Welcome to Planetary Explorer! I'm here to help you find and analyze planetary data. Tell me what you're working on, and we'll get started.",
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
  
  //  Clear local vision session when vision mode is deactivated
  useEffect(() => {
    if (selectedModule !== 'vision' && localVisionSessionId) {
      console.log(' Chat: Vision mode deactivated, clearing local session');
      setLocalVisionSessionId(null);
    }
  }, [selectedModule, localVisionSessionId]);
  
  // Listen for STAC query events from GetStartedButton (clears sessions and processes query)
  useEffect(() => {
    const handleStacQueryEvent = (event: CustomEvent<{ query: string; clearSessions: boolean }>) => {
      const query = event.detail.query;
      if (query && query.trim()) {
        console.log(' Chat: Received STAC query from GetStartedButton:', query);
        
        // Clear local vision session for new STAC search
        if (event.detail.clearSessions && localVisionSessionId) {
          console.log(' Chat: Clearing local vision session for new STAC search');
          setLocalVisionSessionId(null);
        }
        
        // Also call parent callbacks to clear sessions
        if (event.detail.clearSessions) {
          if (onClearVisionSession) {
            console.log(' Chat: Calling onClearVisionSession callback');
            onClearVisionSession();
          }
          if (onClearTerrainSession) {
            console.log(' Chat: Calling onClearTerrainSession callback');
            onClearTerrainSession();
          }
        }
        
        // Set the pending query to trigger processing
        setPendingQuery(query);
      }
    };

    window.addEventListener('planetaryexplorer-stac-query' as any, handleStacQueryEvent as any);
    return () => {
      window.removeEventListener('planetaryexplorer-stac-query' as any, handleStacQueryEvent as any);
    };
  }, [localVisionSessionId, onClearVisionSession, onClearTerrainSession]);
  
  // Listen for regular query events from GetStartedButton (vision queries - keep session)
  useEffect(() => {
    const handleQueryEvent = (event: CustomEvent<{ 
      query: string; 
      analysisType?: 'raster' | 'screenshot';
      requiresVision?: boolean;
      requiresPin?: boolean;
      requiresStacData?: boolean;
    }>) => {
      const { query, analysisType, requiresVision, requiresPin, requiresStacData } = event.detail;
      
      if (query && query.trim()) {
        // Use requestAnimationFrame + setTimeout to ensure React has flushed all pending state updates
        // This fixes a timing issue where mapContext refs were stale when the event fired
        // The extra 50ms delay ensures state propagation from MapView -> MainApp -> Chat is complete
        requestAnimationFrame(() => {
          setTimeout(() => {
            // Use refs to get latest values (avoid stale closure issue)
            const currentSelectedModule = selectedModuleRef.current;
            const currentMapContext = mapContextRef.current;
            
            console.log(' Chat: Received query from GetStartedButton:', query);
            console.log(' Chat: Analysis type hint:', analysisType || 'none');
            console.log(' Chat: Requirements:', { requiresVision, requiresPin, requiresStacData });
            console.log(' Chat: Current state (from refs after 50ms delay) - selectedModule:', currentSelectedModule, 'vision_pin:', currentMapContext?.vision_pin, 'vision_mode:', currentMapContext?.vision_mode);
          
          // ============================================================
          // VALIDATION: Only block when STAC data is genuinely required
          // (vision-style sample queries that need tiles loaded). The
          // "vision module on" / "pin dropped" gates were removed: the
          // backend's AnalysisRouter now picks the right analyzer per
          // turn based on pin / screenshot / loaded_collections, so a
          // pin-bearing question without the Vision module no longer
          // needs to be blocked client-side.
          // ============================================================
          const validationErrors: string[] = [];

          if (requiresStacData) {
            const hasStacData = (currentMapContext?.tile_urls?.length > 0) || (currentMapContext?.stac_items?.length > 0);
            if (!hasStacData) {
              validationErrors.push('**No satellite data loaded.** Please run a STAC Search query (Step 1) first to load tiles on the map.');
            }
          }

          // Suppress unused-var warnings for the now-relaxed flags. They
          // are kept on the event payload so the Get Started panel does
          // not need to change shape.
          void requiresVision;
          void requiresPin;

          // If validation failed, show error message to user
          if (validationErrors.length > 0) {
            console.warn(' Chat: Sample-query validation failed:', validationErrors);
            const errorMessage: ChatMessage = {
              role: 'assistant',
              content: validationErrors.join('\n\n'),
              timestamp: new Date()
            };
            setMessages(prev => [...prev, errorMessage]);
            return; // Don't process the query
          }
          
          // Store the analysis type hint for the upcoming query
          setPendingAnalysisType(analysisType || null);
          // Set the pending query to trigger processing after chatMutation is ready
          setPendingQuery(query);
          }, 50); // 50ms delay to ensure state propagation is complete
        });
      }
    };

    window.addEventListener('planetaryexplorer-query' as any, handleQueryEvent as any);
    return () => {
      window.removeEventListener('planetaryexplorer-query' as any, handleQueryEvent as any);
    };
  }, []); // Empty deps - uses refs for latest values to avoid stale closures
  
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
      console.log(' Chat: Cancelling pending thinking messages');
      setMessages(prev => prev.filter(msg => !msg.isThinking));
    } else if (mobilityAnalysisResult.type === 'thinking') {
      // Show "thinking" animation message - this will be replaced by actual result
      const thinkingMessage: ChatMessage = {
        role: 'assistant',
        content: 'Thinking...',
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
          content: `${mobilityAnalysisResult.message}`,
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
        content: mobilityAnalysisResult.message || 'Analyzing...',
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
        
        // Handle both response formats:
        // 1. Direct: mobilityAnalysisResult.data = { result: { summary: "..." } }
        // 2. Nested: mobilityAnalysisResult.data = { data: { result: { summary: "..." } } }
        const result = mobilityAnalysisResult.data?.result ?? mobilityAnalysisResult.data?.data?.result;
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
      // Fresh AbortController per turn. handleStopMessage calls .abort() on
      // this controller to terminate the in-flight HTTP request end-to-end.
      const controller = new AbortController();
      chatAbortRef.current = controller;
      cancelledRef.current = false;
      try {
        // CRITICAL: Always read the latest map context from the ref.
        // The closure-captured `mapContext` prop can be stale after map navigation.
        const currentMapCtx = mapContextRef.current;

        // ────────────────────────────────────────────────────────────
        // Universal routing: every free-text chat turn now flows through
        // the standard /api/query path. The backend's two-layer router
        // (ActionRouter → AnalysisRouter) re-classifies every turn fresh
        // using `pin`, `vision_mode`, `imagery_base64`, `tile_urls`, and
        // `loaded_collections`, and picks the right analyzer per turn:
        //   • vision           → "what do you see here?"
        //   • raster_sampling  → "what is the value at this pin?"
        //   • llm_only         → general-knowledge fallback
        //   • [raster_sampling, vision] → mixed numeric+descriptive turns
        //
        // The previous code path bound every turn after the first pin
        // drop to a sticky Foundry session on /api/geoint/vision/chat,
        // which could not answer methodology / contextual / non-vision
        // follow-ups and surfaced as "Vision chat failed". Routing every
        // turn through /api/query lets the user freely interleave STAC
        // queries, raster samples, vision descriptions, and contextual
        // questions in any order.
        //
        // The explicit GEOINT module workflows below (terrain, mobility,
        // comparison, building_damage, extreme_weather) are kept because
        // those are user-initiated by clicking a module + dropping pins,
        // and they have their own pinned coordinates / multi-pin state
        // that the generic pipeline does not yet model.
        // ────────────────────────────────────────────────────────────

        // Clear pending analysis-type hint (it was only used by the old
        // vision sidecar; the AnalysisRouter doesn't need it).
        if (pendingAnalysisType) setPendingAnalysisType(null);

        //  TERRAIN CHAT ROUTING
        // Route to terrain agent if:
        // 1. We have an active terrain session with sessionId (follow-up), OR
        // 2. Terrain module is selected and session is initializing (pin placed, API call in flight)
        const terrainSessionNow = terrainSessionRef.current;
        const isTerrainModuleActive = selectedModuleRef.current === 'terrain';
        
        if (terrainSessionNow && (terrainSessionNow.sessionId || isTerrainModuleActive)) {
          const sessionId = terrainSessionNow.sessionId || null; // null creates new session
          const terrainLat = terrainSessionNow.lat;
          const terrainLng = terrainSessionNow.lng;
          
          console.log(' Chat: Routing to terrain agent (session:', sessionId || 'NEW', ')');
          console.log(' Chat: Including screenshot for terrain agent:', !!currentMapCtx?.imagery_base64);
          
          const { sendTerrainChatMessage } = await import('../services/api');
          const result = await sendTerrainChatMessage(
            sessionId,
            message,
            terrainLat,
            terrainLng,
            currentMapCtx?.imagery_base64, // Include screenshot for vision analysis
            5.0
          );
          
          console.log(' Chat: Terrain agent response:', result);
          console.log(' Chat: Tool calls:', result.tool_calls);
          
          // Store session ID for follow-up questions
          if (result.session_id && !terrainSessionNow.sessionId) {
            console.log(' Chat: Storing new terrain session ID:', result.session_id);
            if (onTerrainSessionChange) {
              onTerrainSessionChange({
                sessionId: result.session_id,
                lat: terrainLat,
                lng: terrainLng
              });
            }
          }
          
          // Return terrain agent result (will be handled by onSuccess)
          return {
            response: result.response,
            session_id: result.session_id,
            tool_calls: result.tool_calls,
            isTerrainResponse: true
          };
        }
        
        //  COMPARISON ROUTING
        // Route to comparison agent when comparison module is selected
        if (selectedModule === 'comparison') {
          console.log(' Chat: Routing to comparison agent');
          console.log(' Chat: Query:', message);
          console.log(' Chat: Map context:', {
            lat: currentMapCtx?.vision_pin?.lat || currentPin?.lat,
            lng: currentMapCtx?.vision_pin?.lng || currentPin?.lng
          });
          console.log(' Chat: Including screenshot for comparison agent:', !!currentMapCtx?.imagery_base64);
          
          try {
            const response = await apiService.triggerGeointAnalysis(
              currentMapCtx?.vision_pin?.lat || currentPin?.lat || 0,
              currentMapCtx?.vision_pin?.lng || currentPin?.lng || 0,
              'comparison',
              message, // user_query
              undefined, // userContext
              currentMapCtx?.imagery_base64 || undefined, // screenshot - include map view for visual context
              undefined  // signal
            );
            
            console.log(' Chat: Comparison agent response:', response);
            
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
              let content = '**Temporal Comparison Analysis**\n\n';
              
              if (result.location_name) {
                content += `**Location:** ${result.location_name}\n`;
              }
              
              if (result.before_date && result.after_date) {
                content += `**Time Period:** ${result.before_date} -> ${result.after_date}\n\n`;
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
            console.error(' Chat: Comparison agent error:', error);
            return {
              response: `Comparison analysis failed: ${error.message}`,
              isComparisonResponse: true,
              isError: true
            };
          }
        }
        
        //  MOBILITY ROUTING
        // Route to mobility agent when mobility module is selected and both pins are placed
        if (selectedModule === 'mobility' && mobilityPinCoords) {
          const { pinA, pinB } = mobilityPinCoords;
          
          console.log(' Chat: Routing to mobility agent');
          console.log(' Chat: User question:', message);
          console.log(' Chat: Pin A:', pinA, 'Pin B:', pinB);
          console.log(' Chat: Including screenshot for mobility agent:', !!currentMapCtx?.imagery_base64);
          
          try {
            const response = await apiService.triggerGeointAnalysis(
              pinA.lat,
              pinA.lng,
              'mobility',
              `${message} Analyze traversability from Point A (${pinA.lat.toFixed(4)}, ${pinA.lng.toFixed(4)}) to Point B (${pinB.lat.toFixed(4)}, ${pinB.lng.toFixed(4)}). You MUST use your satellite analysis tools (analyze_directional_mobility, detect_water_bodies, analyze_slope_for_mobility, analyze_vegetation_density, detect_active_fires) at both coordinates. Do NOT answer from general knowledge.`,
              undefined, // userContext
              currentMapCtx?.imagery_base64 || undefined, // screenshot - include map view for visual context
              undefined, // signal
              { latitude_b: pinB.lat, longitude_b: pinB.lng }
            );
            
            console.log(' Chat: Mobility agent response:', response);
            
            const mobilityResponse = response?.result?.response || response?.result?.summary || response?.message || 'Mobility analysis complete.';
            return {
              response: mobilityResponse,
              isMobilityResponse: true
            };
            
          } catch (error: any) {
            console.error(' Chat: Mobility agent error:', error);
            return {
              response: `Mobility analysis failed: ${error.message}`,
              isMobilityResponse: true,
              isError: true
            };
          }
        }
        
        // BUILDING DAMAGE ROUTING
        // Route to building damage agent when building_damage module is selected and pin is dropped
        if (selectedModule === 'building_damage') {
          const lat = currentMapCtx?.vision_pin?.lat || currentPin?.lat || 0;
          const lng = currentMapCtx?.vision_pin?.lng || currentPin?.lng || 0;
          
          console.log(' Chat: Routing to building damage agent');
          console.log(' Chat: Query:', message);
          console.log(' Chat: Coordinates:', { lat, lng });
          console.log(' Chat: Including screenshot for building damage agent:', !!currentMapCtx?.imagery_base64);
          
          try {
            const response = await apiService.triggerGeointAnalysis(
              lat,
              lng,
              'building_damage',
              message, // user_query - the damage assessment question
              undefined, // userContext
              currentMapCtx?.imagery_base64 || undefined, // screenshot - include loaded map imagery
              undefined  // signal
            );
            
            console.log(' Chat: Building damage response:', response);
            
            const damageAnalysis = response?.result?.response || response?.result?.summary || response?.message || 'Building damage analysis complete.';
            return {
              response: damageAnalysis,
              isBuildingDamageResponse: true
            };
            
          } catch (error: any) {
            console.error(' Chat: Building damage error:', error);
            return {
              response: `Building damage analysis failed: ${error.message}`,
              isBuildingDamageResponse: true,
              isError: true
            };
          }
        }
        
        //  EXTREME WEATHER ROUTING
        // Route to extreme weather agent when extreme_weather module is selected and pin is dropped
        if (selectedModule === 'extreme_weather') {
          const lat = currentMapCtx?.vision_pin?.lat || currentPin?.lat || 0;
          const lng = currentMapCtx?.vision_pin?.lng || currentPin?.lng || 0;
          
          console.log(' Chat: Routing to extreme weather agent');
          console.log(' Chat: Query:', message);
          console.log(' Chat: Coordinates:', { lat, lng });
          console.log(' Chat: Including screenshot for extreme weather agent:', !!currentMapCtx?.imagery_base64);
          
          try {
            const response = await apiService.triggerGeointAnalysis(
              lat,
              lng,
              'extreme_weather',
              message, // user_query - the climate question
              undefined, // userContext
              currentMapCtx?.imagery_base64 || undefined, // screenshot - include map view for visual context
              undefined  // signal
            );
            
            console.log(' Chat: Extreme weather response:', response);
            console.log(' Chat: response.result:', response.result);
            console.log(' Chat: response.result?.analysis:', response.result?.analysis);
            console.log(' Chat: response.result?.analysis length:', response.result?.analysis?.length);
            console.log(' Chat: response.result?.tool_calls:', response.result?.tool_calls);
            
            // Return the response content
            // API returns { status, result: { analysis, tool_calls, message_count }, session_id, timestamp }
            const climateAnalysis = response.result?.analysis || response.message || response.content || 'Extreme weather analysis complete.';
            return {
              response: climateAnalysis,
              isExtremeWeatherResponse: true
            };
            
          } catch (error: any) {
            console.error(' Chat: Extreme weather error:', error);
            return {
              response: `Extreme weather analysis failed: ${error.message}`,
              isExtremeWeatherResponse: true,
              isError: true
            };
          }
        }

        //  RESILIENCE ROUTING
        // Region-scoped MAF workflow (no pin). Calls /api/resilience/assess with
        // the user's natural-language query, hands the dossier off to the chat,
        // and dispatches `resilience:facilities` so MapView can drop the
        // severity-colored circle markers.
        //
        // IMPORTANT: read the module from the ref, not the closure-captured
        // `selectedModule` prop. The mutationFn closure is created at render
        // time; if the user toggles the module right before sending, the
        // captured value can lag the actual state and the message falls
        // through to the generic /api/query path (which is why some queries
        // came back as "Loading imagery…" instead of running the planner).
        const _activeModule = selectedModuleRef.current || selectedModule;
        if (_activeModule === 'resilience') {
          // NOTE: the old frontend clarify-guard that demanded a region /
          // hazard / horizon keyword has been removed. The MAF planner now
          // defaults to the investigative route and handles ambiguity,
          // specific-facility outage questions ("if Houston port goes
          // offline…"), and free-form analyst asks far better than a
          // regex match here can. Sending everything straight to the
          // planner also lets it call `simulate_outage`, `query_facilities`,
          // and the MPC tools instead of the frontend deciding for it.
          // Region heuristic — default TX (where the seed lakehouse rows live).
          // If the user mentions another US state name, narrow to that.
          const REGION_HINTS: Record<string, string> = {
            ' tx': 'TX', 'texas': 'TX',
            ' ca': 'CA', 'california': 'CA',
            ' az': 'AZ', 'arizona': 'AZ',
            ' or': 'OR', 'oregon': 'OR',
            ' wa': 'WA', 'washington': 'WA',
            ' ny': 'NY', 'new york': 'NY',
          };
          let regionFilter: string | undefined = 'TX';
          const lower = (message || '').toLowerCase();
          for (const [needle, code] of Object.entries(REGION_HINTS)) {
            if (lower.includes(needle)) { regionFilter = code; break; }
          }
          // Hazard heuristic — keep both unless the user is clearly narrowing.
          const hazards: string[] = [];
          if (/heat|hot|temperature|cooling|dome/i.test(message || '')) hazards.push('heat');
          if (/fire|wildfire|smoke|pm2|air quality|aqi/i.test(message || '')) hazards.push('wildfire');
          const hazardsFinal = hazards.length > 0 ? hazards : ['heat', 'wildfire'];
          // Horizon heuristic — "next 14 days" / "two-week" → 14, else default 7.
          let horizonDays = 7;
          const daysMatch = (message || '').match(/(\d{1,2})\s*(?:day|d\b)/i);
          if (daysMatch) {
            const n = parseInt(daysMatch[1], 10);
            if (n > 0 && n <= 14) horizonDays = n;
          } else if (/two[-\s]?week|fortnight/i.test(message || '')) {
            horizonDays = 14;
          }

          console.log(' Chat: Routing to Resilience', { regionFilter, hazards: hazardsFinal, horizonDays });

          // Always go through the planner (smart endpoint). The Resilience
          // agent is a true MAF agent — non-deterministic planner that can
          // combine Fabric facility data with Microsoft Planetary Computer
          // public STAC imagery (dynamic collection routing) and synthesize
          // a conversational markdown answer in `dossier.narrative`. The
          // backend router still falls through to the deterministic DAG
          // for trivial "refresh the dossier" asks, but the default is the
          // planner because it produces a richer, better-grounded answer.
          const useSmart = true;

          try {
            // Reset per-turn trace state and stream the assessment so
            // every MCP call surfaces as a tool_call / tool_result
            // SSE event. The final dossier is emitted as a `dossier`
            // event when the planner returns.
            activeTrace.clear();
            const collectedRows: any[] = [];
            const dossier = await apiService.streamResilienceAssessment(
              {
                regionFilter,
                horizonDays,
                hazards: hazardsFinal,
                userQuery: message,
              },
              {
                onTrace: (evt) => {
                  activeTrace.ingest(evt);
                  // Mirror ingest into a local accumulator so we can
                  // attach the final row list to the chat message.
                  if (evt?.type === 'tool_call') {
                    collectedRows.push({
                      traceId: evt.trace_id,
                      serverId: evt.server_id,
                      tool: evt.tool,
                      tier: evt.tier,
                      args: evt.args || {},
                      status: 'pending',
                    });
                  } else if (evt?.type === 'tool_result') {
                    const idx = collectedRows.findIndex((r) => r.traceId === evt.trace_id);
                    const denied = evt.error === 'denied_by_user';
                    const merged = {
                      traceId: evt.trace_id,
                      serverId: evt.server_id,
                      tool: evt.tool,
                      tier: evt.tier,
                      args: evt.args || {},
                      status: denied ? 'denied' : evt.ok ? 'ok' : 'error',
                      latencyMs: evt.latency_ms,
                      responseSummary: evt.response_summary,
                      error: evt.error,
                    };
                    if (idx >= 0) collectedRows[idx] = merged;
                    else collectedRows.push(merged);
                  }
                },
                onConfirmRequest: (evt) => {
                  setPendingConfirms((prev) => {
                    if (prev.some((p) => p.traceId === evt.trace_id)) return prev;
                    return [
                      ...prev,
                      {
                        traceId: evt.trace_id,
                        serverId: evt.server_id,
                        tool: evt.tool,
                        tier: evt.tier,
                        args: evt.args || {},
                      },
                    ];
                  });
                },
                onConfirmResolved: (evt) => {
                  setPendingConfirms((prev) => prev.filter((p) => p.traceId !== evt.trace_id));
                },
                onError: (err) => console.warn(' Resilience stream error event:', err),
              },
            );
            if (!dossier) {
              // Stream closed without a terminal dossier event — fall
              // back to the buffered endpoint so the user still gets an
              // answer.
              console.warn(' Resilience stream returned no dossier; falling back to buffered call.');
              return {
                response: 'Resilience stream ended without a final dossier. Please retry.',
                isResilienceResponse: true,
                isError: true,
              };
            }

            // Dispatch facility markers to the map (MapView already listens).
            const facilities: any[] = Array.isArray(dossier?.facilities) ? dossier.facilities : [];
            try {
              window.dispatchEvent(new CustomEvent('resilience:facilities', { detail: { facilities, dossier } }));
            } catch (e) {
              console.warn(' Chat: failed to dispatch resilience:facilities event', e);
            }

            // Format the dossier for chat — mirror Site Intel one-line
            // citation rows (Fabric Lakehouse · `table` (N rows · vK)) so the
            // eye scans Fabric / AI Search / Open-Meteo rows uniformly across
            // the two agents.
            const provenance: any[] = Array.isArray(dossier?.provenance) ? dossier.provenance : [];
            const sevLabel = (s: string) => ({
              severe: 'SEVERE',
              high: 'HIGH',
              moderate: 'MOD',
              low: 'LOW',
            }[String(s || '').toLowerCase()] || '—');
            const fmtScore = (v: any) => (typeof v === 'number' && isFinite(v) ? v.toFixed(0) : '—');

            const lines: string[] = [];
            const regionLabel = regionFilter || 'All regions';
            // Show which path the backend actually ran (planner can decline
            // the smart hint if the router classifies the query as standard,
            // and the standard endpoint never sets `route`).
            const route: string = String(dossier?.route || (useSmart ? 'investigative' : 'standard'));
            const routeBadge = route === 'investigative' ? ' · _via planner_' : '';
            lines.push(`**Resilience · ${regionLabel} · ${horizonDays}-day horizon · ${hazardsFinal.join(' + ')}**${routeBadge}`);

            // Planner runs return a free-form narrative answer — render it
            // first so the user sees the synthesised answer before the
            // structured facility table. dossier.summary may either be the
            // standard summary object OR (planner) a plain string.
            if (route === 'investigative' && typeof dossier?.narrative === 'string' && dossier.narrative.trim()) {
              lines.push('');
              lines.push(dossier.narrative.trim());
            } else if (route === 'investigative' && typeof dossier?.summary === 'string' && dossier.summary.trim()) {
              lines.push('');
              lines.push(dossier.summary.trim());
            }

            // dossier.summary is an OBJECT {facilities_assessed, at_risk_facilities, top_risks}.
            // Compose a one-line human header from it instead of stringifying.
            const sumObj = (dossier && typeof dossier.summary === 'object' && dossier.summary) || {};
            const assessed = Number(sumObj.facilities_assessed ?? facilities.length) || 0;
            const atRisk = Number(sumObj.at_risk_facilities ?? 0) || 0;
            const topPick = Array.isArray(sumObj.top_risks) && sumObj.top_risks[0]
              ? sumObj.top_risks[0]
              : null;
            if (assessed > 0) {
              const lead = topPick
                ? ` · top: **${topPick.name || topPick.facility_id}** (${sevLabel(topPick.severity)})`
                : '';
              lines.push('');
              lines.push(`> **${atRisk} of ${assessed} facilities at risk**${lead}.`);
            }
            lines.push('');

            // Rank by overall_risk desc (the field the backend actually emits;
            // the earlier formatter looked for `score` which doesn't exist on
            // the dossier shape, so every row rendered as "score —").
            const sorted = [...facilities].sort(
              (a, b) => (Number(b?.overall_risk) || 0) - (Number(a?.overall_risk) || 0)
            );
            const top = sorted.slice(0, 5);
            const remaining = sorted.length - top.length;

            if (top.length > 0) {
              // Render as a bullet list instead of a markdown table — the
              // chat panel's narrow column wraps tables into an unreadable
              // wall of pipes. Each facility becomes a short bullet with a
              // nested sub-line for peak + driver + cascade, which the
              // markdown renderer turns into a clean indented item.
              lines.push(`**Top at-risk facilities** (${assessed || facilities.length} assessed)`);
              lines.push('');
              top.forEach((f, i) => {
                const name = f?.name || f?.facility_id || 'facility';
                const score = fmtScore(f?.overall_risk);
                const sev = sevLabel(f?.severity);
                const h = f?.hazards || {};
                const primary = f?.primary_hazard && h[f.primary_hazard] ? h[f.primary_hazard] : (h.heat || h.wildfire || {});
                const peakBits: string[] = [];
                if (typeof primary.peak_value === 'number') {
                  const unit = (f?.primary_hazard === 'wildfire') ? '' : ' °F';
                  peakBits.push(`peak ${primary.peak_value.toFixed(0)}${unit}`);
                }
                if (primary.peak_day) peakBits.push(`on ${String(primary.peak_day).slice(5)}`);
                const peakStr = peakBits.length ? peakBits.join(' ') : '';
                // Driver string — first non-empty driver, fallback to summary.
                const driver = Array.isArray(primary.drivers) && primary.drivers.length
                  ? primary.drivers[0]
                  : (primary.summary || '');
                const downstream = Array.isArray(f?.downstream) ? f.downstream.length : 0;
                const upstream = Array.isArray(f?.upstream_at_risk) ? f.upstream_at_risk.length : 0;
                const cascade = downstream > 0
                  ? `${downstream} downstream site${downstream === 1 ? '' : 's'} at risk`
                  : (upstream > 0 ? `${upstream} upstream supplier${upstream === 1 ? '' : 's'} at risk` : '');

                // Lead bullet: "1. **Facility Name** — **62 · HIGH**"
                lines.push(`${i + 1}. **${name}** — **${score} · ${sev}**`);
                // Sub-bullets: only emit the ones we actually have data for.
                const subs: string[] = [];
                if (peakStr) subs.push(peakStr);
                if (driver) subs.push(driver);
                if (cascade) subs.push(cascade);
                for (const s of subs) {
                  lines.push(`   - ${s}`);
                }
              });
              if (remaining > 0) {
                lines.push('');
                lines.push(`*…and ${remaining} more lower-risk facilit${remaining === 1 ? 'y' : 'ies'} — see map markers.*`);
              }

              // Recommended actions (collapsible) — pulls playbook titles +
              // snippets from the top at-risk facilities. Acts as the
              // "what should we do first?" answer the user asked for.
              const actionRows: { facility: string; title: string; snippet: string; url?: string }[] = [];
              const seen = new Set<string>();
              for (const f of top) {
                const pbs = Array.isArray(f?.playbooks) ? f.playbooks.slice(0, 2) : [];
                for (const pb of pbs) {
                  const title = (pb?.title || pb?.id || 'Playbook') as string;
                  const key = `${f?.facility_id}::${title}`;
                  if (seen.has(key)) continue;
                  seen.add(key);
                  const snippet = (pb?.snippet || '').toString().slice(0, 180);
                  actionRows.push({
                    facility: f?.name || f?.facility_id || 'facility',
                    title,
                    snippet,
                    url: pb?.url || undefined,
                  });
                }
              }
              if (actionRows.length > 0) {
                lines.push('');
                lines.push('**Recommended actions**');
                for (const a of actionRows.slice(0, 6)) {
                  const link = a.url ? ` · [doc](${a.url})` : '';
                  const snip = a.snippet ? ` — ${a.snippet}${a.snippet.length >= 180 ? '…' : ''}` : '';
                  lines.push(`- **${a.facility}** → *${a.title}*${snip}${link}`);
                }
              }
            } else {
              lines.push('_No facilities returned. Check Fabric lakehouse seeding or region filter._');
            }

            if (provenance.length > 0) {
              // Single "Sources" section — each row is the identifier the
              // analyst would cite (Fabric table name, AI Search index,
              // MPC collection id, Open-Meteo endpoint), linked when we
              // have a deep link. The narrative above carries the prose;
              // these are the footnotes.
              const sourceRows: string[] = [];
              const seenRows = new Set<string>();
              const pushUnique = (row: string) => {
                if (seenRows.has(row)) return;
                seenRows.add(row);
                sourceRows.push(row);
              };
              for (const p of provenance) {
                if (p.source === 'facility_registry' || p.source === 'supply_edges' || p.source === 'bcp_playbooks') {
                  // Fabric Lakehouse table — no deep link available, just
                  // the table name. Skip 0-row playbook entries entirely
                  // (they were searched but contributed nothing).
                  if (p.source === 'bcp_playbooks' && !p.rows) continue;
                  const where = p.lakehouse === 'fabric' ? 'Fabric Lakehouse' : 'Seed data';
                  pushUnique(`- ${where} · \`${p.source}\``);
                } else if (p.source === 'ai_search') {
                  // Drop phantom rows (skipped/errored/zero-hit) so we
                  // don't cite a search that contributed nothing.
                  if (p.skipped || p.error || !p.hits) continue;
                  pushUnique(`- Azure AI Search · \`${p.index || 'bcp'}\``);
                } else if (p.source === 'open-meteo' || p.source === 'open_meteo') {
                  // Prefer a deep link to the actual query; fall back to docs.
                  const label = p.endpoint ? `Open-Meteo (${p.endpoint})` : 'Open-Meteo';
                  const url = p.citation_url || p.docs_url;
                  pushUnique(url ? `- [${label}](${url})` : `- ${label}`);
                } else if (p.source === 'mpc_public_stac' || p.source === 'mpc_pro_mcp') {
                  // MPC STAC collection — link to the public dataset page
                  // when we have a collection id (mpc_public_stac only).
                  const collection = p.collection || p.collection_id;
                  const network = p.source === 'mpc_pro_mcp' ? 'MPC Pro' : 'MPC STAC';
                  if (collection && p.source === 'mpc_public_stac') {
                    const url = `https://planetarycomputer.microsoft.com/dataset/${encodeURIComponent(collection)}`;
                    pushUnique(`- [${network} · \`${collection}\`](${url})`);
                  } else if (collection) {
                    pushUnique(`- ${network} · \`${collection}\``);
                  } else {
                    pushUnique(`- ${network}`);
                  }
                } else if (p.index) {
                  pushUnique(`- Azure AI Search · \`${p.index}\``);
                } else if (p.source) {
                  pushUnique(`- ${p.source}`);
                }
              }
              if (sourceRows.length > 0) {
                lines.push('');
                lines.push('**Sources**');
                lines.push(...sourceRows);
              }
            }

            // Planner trace footer — collapsed list of tool calls so the
            // user can see *how* the answer was produced. Only present
            // when the investigative path actually ran.
            const trace: any[] = Array.isArray(dossier?.tool_trace) ? dossier.tool_trace : [];
            if (route === 'investigative' && trace.length > 0) {
              lines.push('');
              lines.push(`**Reasoning trace** (${trace.length} tool call${trace.length === 1 ? '' : 's'})`);
              for (const t of trace) {
                const argKeys = t?.args && typeof t.args === 'object' ? Object.keys(t.args).join(', ') : '';
                lines.push(`- hop ${t?.hop ?? '?'} · \`${t?.tool || 'unknown'}\`${argKeys ? ` (${argKeys})` : ''}`);
              }
            }
            if (dossier?.planner_warning) {
              lines.push('');
              lines.push(`> _Planner warning: ${dossier.planner_warning}._`);
            }

            return {
              response: lines.join('\n'),
              isResilienceResponse: true,
              dossier,
              toolTrace: collectedRows,
            };
          } catch (error: any) {
            console.error(' Chat: Resilience error:', error);
            return {
              response: `Resilience assessment failed: ${error.message}`,
              isResilienceResponse: true,
              isError: true
            };
          }
        }

        //  SITE AUDIT ROUTING
        // Route to /api/sites/audit when site_audit module is selected and pin is dropped.
        // Backend body shape is {lat, lng, claimed_mw}; we parse claimed MW from the user
        // query (e.g. "audit a 200 MW site"); default 200 MW.
        if (selectedModule === 'site_audit') {
          // Prefer an explicit pin (vision-mode pin or generic dropped pin).
          // Fall back to the current map center so a geocode pan (e.g. user
          // typed "Midland, Texas" → "Navigating the map to Midland, Texas.")
          // is treated as an implicit pin, instead of bouncing with
          // "Site Intel needs a pin." The (0,0) guard below still catches
          // the truly-unset case (map never moved).
          const centerLat = (currentMapCtx as any)?.bounds?.center_lat;
          const centerLng = (currentMapCtx as any)?.bounds?.center_lng;
          const lat = currentMapCtx?.vision_pin?.lat || currentPin?.lat
            || (Number.isFinite(centerLat) ? centerLat : 0);
          const lng = currentMapCtx?.vision_pin?.lng || currentPin?.lng
            || (Number.isFinite(centerLng) ? centerLng : 0);

          let claimedMw = 200;
          let mwExplicit = false;
          const mwMatch = (message || '').match(/(\d+(?:\.\d+)?)\s*(?:mw|megawatt)/i);
          if (mwMatch) {
            const parsed = parseFloat(mwMatch[1]);
            if (!isNaN(parsed) && parsed > 0) {
              claimedMw = parsed;
              mwExplicit = true;
            }
          }

          // Clarify-guard: site audit produces garbage scoring at (0,0)
          // and silently defaults to a 200 MW asset capacity when the user
          // just said "audit a site". Refuse to call the backend until
          // both inputs are real. Matches the Resilience agent's
          // "ask one focused question" pattern from instructions.md.
          if (lat === 0 && lng === 0) {
            return {
              response: [
                '**Site Intel needs a pin.**',
                '',
                'Drop a pin on the map at the candidate site and resend, or tell me a place name (e.g. "score a 230 kV substation near Ashburn, VA" or "audit a 250 MW solar + BESS site near Midland, TX") and I\'ll geocode it.',
                '',
                "I won't score (0°, 0°) — it's in the Atlantic and the result would be meaningless.",
              ].join('\n'),
              isSiteAuditResponse: true,
              isClarification: true,
            };
          }
          if (!mwExplicit && !/audit|score|rank|assess|evaluate/i.test(message || '')) {
            // Silent default is fine when the user explicitly asked to
            // "audit"/"score"/"evaluate" — the dossier is the answer. But
            // if the message is vague ("look at this site"), ask which
            // asset size they're sizing for before burning the MPC +
            // Fabric calls (water + interconnection weights vary by size).
            return {
              response: [
                '**How large an asset are you sizing for?**',
                '',
                'Pick one and resend (the audit weights interconnection, water, and hazards differently by capacity):',
                '- "audit a 50 MW site" — distribution-scale solar / BESS / small substation',
                '- "audit a 200 MW site" — utility-scale generation or sub-transmission asset (default)',
                '- "audit a 500 MW site" — large generation / 230 kV substation / transmission tap',
                '- "audit a 1000 MW site" — gigawatt-scale plant / 500 kV interconnection',
              ].join('\n'),
              isSiteAuditResponse: true,
              isClarification: true,
            };
          }

          console.log(' Chat: Routing to Site Audit', { lat, lng, claimedMw, query: message });

          try {
            const dossier = await apiService.triggerSiteAudit(lat, lng, claimedMw, message);
            console.log(' Chat: Site audit dossier:', dossier);

            // Format dossier as markdown
            const s = dossier?.scores || {};
            const sum = dossier?.summaries || {};
            const evidence = Array.isArray(dossier?.evidence) ? dossier.evidence : [];
            const provenance = Array.isArray(dossier?.data_provenance) ? dossier.data_provenance : [];

            const fmt = (v: any) => (typeof v === 'number' ? v.toFixed(1) : String(v ?? '—'));
            // Format a Fabric Lakehouse row as a single inline citation
            // bullet, matching the existing SourceChips convention (the
            // source name comes first, then the row payload, then a link
            // when one is available). Returns null when the kind is not a
            // Fabric/permit row so the caller can fall through to MPC
            // handling.
            const fabricRowLine = (e: any): string | null => {
              const k = e?.kind || '';
              const name = e?.name || e?.title || e?.id || '(unnamed)';
              const dist = typeof e?.distance_mi === 'number' ? `${e.distance_mi.toFixed(1)} mi` : null;
              const linkable = (label: string, url?: string) => (url ? `[${label}](${url})` : label);
              switch (k) {
                case 'nearest_substation':
                case 'power_substation':
                case 'transmission_line': {
                  const kv = e?.voltage_kv ? `${e.voltage_kv} kV` : null;
                  const parts = [name, kv, dist].filter(Boolean).join(' · ');
                  return `- Fabric · power · ${parts}${e?.source_url ? ` · ${linkable('source', e.source_url)}` : ''}`;
                }
                case 'nearest_water':
                case 'water_asset': {
                  const huc = e?.huc_code ? `HUC ${e.huc_code}` : null;
                  const parts = [name, huc, dist].filter(Boolean).join(' · ');
                  return `- Fabric · water · ${parts}${e?.source_url ? ` · ${linkable('source', e.source_url)}` : ''}`;
                }
                case 'nearest_data_center':
                case 'existing_data_center': {
                  const mw = e?.capacity_mw ? `${e.capacity_mw} MW` : null;
                  const parts = [name, mw, dist].filter(Boolean).join(' · ');
                  return `- Fabric · data center · ${parts}${e?.source_url ? ` · ${linkable('source', e.source_url)}` : ''}`;
                }
                case 'candidate_site_match':
                case 'parcel_match': {
                  const parts = [name, dist].filter(Boolean).join(' · ');
                  return `- Fabric · candidate site · ${parts}${e?.source_url ? ` · ${linkable('source', e.source_url)}` : ''}`;
                }
                case 'permitting_doc': {
                  const meta = [e?.doc_type, e?.state, e?.doc_date, dist]
                    .filter(Boolean)
                    .join(' · ');
                  const score = typeof e?.search_score === 'number' ? `score ${e.search_score.toFixed(2)}` : null;
                  const tail = [meta, score].filter(Boolean).join(' · ');
                  return `- AI Search · "${name}"${tail ? ` · ${tail}` : ''}${e?.source_url ? ` · ${linkable('doc', e.source_url)}` : ''}`;
                }
                default:
                  return null;
              }
            };
            // MPC evidence rows -> "Public PC · <collection> · item <id>
            // (<datetime>) · [dataset](<url>)". Matches the SourceChips
            // wording ("Public PC" / "MPC Pro") so the audit citations
            // read the same as the routing chip the user already knows.
            const mpcRowLine = (e: any): string | null => {
              const k = e?.kind || '';
              if (k !== 'mpc_land_cover' && k !== 'mpc_elevation' && k !== 'mpc_surface_water' && k !== 'mpc_dynamic_match') {
                return null;
              }
              const cid = e?.collection;
              if (!cid) return null;
              const datasetUrl = `https://planetarycomputer.microsoft.com/dataset/${cid}`;
              const itemUrl = e?.item_id
                ? `https://planetarycomputer.microsoft.com/api/stac/v1/collections/${cid}/items/${e.item_id}`
                : null;
              const payload = (() => {
                if (k === 'mpc_land_cover') return e?.class_name ? `land cover: ${e.class_name}` : 'land cover';
                if (k === 'mpc_elevation') return typeof e?.elevation_m === 'number' ? `elevation ${e.elevation_m} m` : 'elevation';
                if (k === 'mpc_surface_water') return typeof e?.occurrence_pct === 'number' ? `surface-water occurrence ${e.occurrence_pct}%` : 'surface-water occurrence';
                return 'query-matched';
              })();
              const itemPart = e?.item_id
                ? ` · item \`${e.item_id}\`${e?.item_datetime ? ` (${e.item_datetime.slice(0, 10)})` : ''}`
                : (e?.note ? ` · ${e.note}` : '');
              const links = [
                `[dataset](${datasetUrl})`,
                itemUrl ? `[STAC item](${itemUrl})` : null,
              ].filter(Boolean).join(' · ');
              return `- Public PC · ${cid} · ${payload}${itemPart} · ${links}`;
            };
            // Open-Meteo weather climatology row. Same one-line citation
            // shape as Fabric / MPC so the eye scans them uniformly:
            // "Open-Meteo (ERA5) · <year> · <indicators> · [source](...)".
            const weatherRowLine = (e: any): string | null => {
              if (e?.kind !== 'weather_climatology') return null;
              const yr = e?.reference_year ? `${e.reference_year}` : 'climatology';
              const bits: string[] = [];
              if (typeof e?.max_temp_c === 'number') bits.push(`max ${e.max_temp_c}°C`);
              if (typeof e?.days_over_35c === 'number') bits.push(`${e.days_over_35c} d ≥35°C`);
              if (typeof e?.annual_precip_mm === 'number') bits.push(`${e.annual_precip_mm} mm precip`);
              if (typeof e?.max_wind_kmh === 'number') bits.push(`peak wind ${e.max_wind_kmh} km/h`);
              const link = e?.citation_url ? ` · [source](${e.citation_url})` : '';
              return `- Open-Meteo (ERA5) · ${yr} · ${bits.join(' · ') || 'no daily data'}${link}`;
            };

            // Verdict helper. Thresholds mirror typical siting-team rubric:
            // ≥75 strong, 55–74 viable, 35–54 marginal, <35 weak. Plain text
            // labels (no emoji) per product direction.
            const verdictFor = (v: any): string => {
              const n = typeof v === 'number' ? v : Number(v);
              if (!Number.isFinite(n)) return 'UNRATED';
              if (n >= 75) return 'STRONG';
              if (n >= 55) return 'VIABLE';
              if (n >= 35) return 'MARGINAL';
              return 'WEAK';
            };
            // Flag low-confidence findings inline so the user knows not
            // to fully trust the dimension. Today: io-lulc class_0 is a
            // no-data/water-mask pixel — silently scoring it is misleading.
            const decorateSummary = (text: string): string => {
              if (!text) return '';
              let out = String(text);
              // Highlight io-lulc class_0 as indeterminate (no-data pixel).
              out = out.replace(/land cover at point:\s*class_0/gi, 'land cover indeterminate (class_0, no-data pixel)');
              return out;
            };

            // Rank dimensions by score so we can call out top blockers
            // and strengths in the verdict line.
            const dims: Array<{ key: string; label: string; weight: number; score: number }> = [
              { key: 'power', label: 'Power', weight: 35, score: Number(s.power) },
              { key: 'water', label: 'Water', weight: 15, score: Number(s.water) },
              { key: 'hazards', label: 'Hazards', weight: 15, score: Number(s.hazards) },
              { key: 'competition', label: 'Competition', weight: 10, score: Number(s.competition) },
              { key: 'parcel_match', label: 'Parcel', weight: 10, score: Number(s.parcel_match) },
              { key: 'precedent', label: 'Precedent', weight: 15, score: Number(s.precedent) },
            ].filter((d) => Number.isFinite(d.score));
            const sortedAsc = [...dims].sort((a, b) => a.score - b.score);
            const blockers = sortedAsc.slice(0, 2).filter((d) => d.score < 55);
            const strengths = [...dims].sort((a, b) => b.score - a.score).slice(0, 2).filter((d) => d.score >= 60);

            const lines: string[] = [];
            lines.push(`**Site Intel · ${lat.toFixed(4)}°, ${lng.toFixed(4)}° · ${claimedMw} MW asset capacity**`);
            lines.push('');

            // Verdict header — label + score in one line, followed by a
            // compact blockers/strengths cue.
            const overallNum = Number(s.overall);
            lines.push(`**${verdictFor(s.overall)} · ${fmt(s.overall)} / 100**`);
            const cue: string[] = [];
            if (blockers.length > 0) {
              cue.push(`Blockers: ${blockers.map((d) => `${d.label} (${d.score.toFixed(0)})`).join(', ')}`);
            }
            if (strengths.length > 0) {
              cue.push(`Strengths: ${strengths.map((d) => `${d.label} (${d.score.toFixed(0)})`).join(', ')}`);
            }
            if (cue.length > 0) lines.push(`*${cue.join(' · ')}*`);
            lines.push('');

            // Dimension scores — bold label + score + weight, with
            // low-confidence inline flags woven into the summary text.
            lines.push('**Dimension scores**');
            for (const d of dims) {
              const sm = decorateSummary((sum as any)[d.key] || '');
              lines.push(`- **${d.label}** · ${d.score.toFixed(1)} (${d.weight}%)${sm ? ` — ${sm}` : ''}`);
            }

            // Build inline citations grouped by source class. Truncate
            // each group to the top 3 most relevant rows (Fabric uses
            // input order which is already distance-sorted upstream;
            // AI Search uses search_score; PC uses dataset order).
            if (evidence.length > 0) {
              const fabricLines: string[] = [];
              const aiSearchLines: string[] = [];
              const mpcLines: string[] = [];
              const weatherLines: string[] = [];
              const leftover: Record<string, number> = {};
              for (const e of evidence) {
                const f = fabricRowLine(e);
                if (f) {
                  if (e?.kind === 'permitting_doc') aiSearchLines.push(f);
                  else fabricLines.push(f);
                  continue;
                }
                const m = mpcRowLine(e);
                if (m) {
                  // Inline confidence flag on no-data LULC pixels.
                  mpcLines.push(m.replace(/land cover: class_0/gi, 'land cover: indeterminate (class_0)'));
                  continue;
                }
                const w = weatherRowLine(e);
                if (w) { weatherLines.push(w); continue; }
                const k = (e && e.kind) || 'other';
                leftover[k] = (leftover[k] || 0) + 1;
              }
              // AI Search: re-rank by search_score desc so the most
              // relevant doc surfaces first regardless of backend order.
              const permitEvidence = evidence.filter((e: any) => e?.kind === 'permitting_doc');
              const sortedPermit = [...permitEvidence].sort(
                (a: any, b: any) => (b?.search_score ?? 0) - (a?.search_score ?? 0)
              );
              const sortedAiSearchLines = sortedPermit
                .map((e) => fabricRowLine(e))
                .filter((x): x is string => !!x);
              const aiSearchFinal = sortedAiSearchLines.length > 0 ? sortedAiSearchLines : aiSearchLines;

              const TOP_N = 3;
              const pushGroup = (header: string, rows: string[]) => {
                if (rows.length === 0) return;
                lines.push('');
                lines.push(`**${header}**`);
                lines.push(...rows.slice(0, TOP_N));
                if (rows.length > TOP_N) lines.push(`*… ${rows.length - TOP_N} more*`);
              };

              pushGroup('Evidence · Fabric Lakehouse', fabricLines);
              pushGroup('Evidence · Azure AI Search (permitting)', aiSearchFinal);
              pushGroup('Evidence · Planetary Computer', mpcLines);
              pushGroup('Evidence · Live Weather', weatherLines);

              if (Object.keys(leftover).length > 0) {
                const leftoverBits = Object.entries(leftover).map(([k, n]) => `${k}: ${n}`).join(' · ');
                lines.push('');
                lines.push(`*Additional signals — ${leftoverBits}*`);
              }
            }

            // Single Sources footer — replaces the old "Data provenance"
            // section (which duplicated Evidence citations). Counts each
            // backing dataset so the reader sees the surface area at a
            // glance without re-reading the per-row citations.
            if (provenance.length > 0) {
              const fabricRows = provenance.filter((p: any) => p.source === 'fabric_lakehouse' || p.table);
              const pcCollections = new Set<string>();
              const aiIndices = new Set<string>();
              let weatherCount = 0;
              for (const p of provenance) {
                if (p?.source === 'planetary_computer') {
                  if (p.collection) pcCollections.add(p.collection);
                  if (Array.isArray(p.collections)) p.collections.forEach((c: string) => pcCollections.add(c));
                } else if (p?.source === 'open_meteo') {
                  weatherCount++;
                } else if (p?.index) {
                  aiIndices.add(p.index);
                }
              }
              const totalRows = fabricRows.reduce(
                (acc: number, p: any) => acc + (typeof p.rows === 'number' ? p.rows : 0),
                0
              );
              const fmtCount = (n: number) =>
                n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n);
              const parts: string[] = [];
              if (fabricRows.length > 0) {
                parts.push(`Fabric Lakehouse (${fabricRows.length} table${fabricRows.length === 1 ? '' : 's'} · ${fmtCount(totalRows)} rows)`);
              }
              if (pcCollections.size > 0) {
                parts.push(`Planetary Computer (${pcCollections.size} collection${pcCollections.size === 1 ? '' : 's'})`);
              }
              if (weatherCount > 0) parts.push('Open-Meteo ERA5');
              if (aiIndices.size > 0) {
                parts.push(`Azure AI Search (\`${Array.from(aiIndices).join('`, `')}\`)`);
              }
              if (parts.length > 0) {
                lines.push('');
                lines.push(`**Sources:** ${parts.join(' · ')}`);
              }
            }

            // Closing determination paragraph — a coherent narrative the
            // analyst can paste into a memo. Pulls the top strength + top
            // blocker + score-bucket recommendation into one sentence.
            if (dims.length > 0 && Number.isFinite(overallNum)) {
              const verdict = verdictFor(overallNum);
              const topStrength = strengths[0];
              const topBlocker = blockers[0];
              const recByVerdict: Record<string, string> = {
                STRONG: 'Recommend advancing to a Phase 1 feasibility study and initiating utility interconnection screening.',
                VIABLE: 'Recommend a targeted Phase 1 study scoped to resolve the flagged constraints before committing capital.',
                MARGINAL: 'Recommend deferring commitment pending mitigation of the flagged constraints; consider a paired alternate site.',
                WEAK: 'Recommend deprioritizing this site in favor of stronger candidates in the portfolio.',
                UNRATED: 'Insufficient signal to make a siting determination at this time.',
              };
              const rec = recByVerdict[verdict] ?? recByVerdict.UNRATED;
              const strengthClause = topStrength
                ? `${topStrength.label.toLowerCase()} (${topStrength.score.toFixed(0)})`
                : 'no standout strengths';
              const blockerClause = topBlocker
                ? `${topBlocker.label.toLowerCase()} (${topBlocker.score.toFixed(0)})`
                : 'no material blockers';
              const determination =
                `**Determination.** Composite score ${overallNum.toFixed(1)} / 100 places this site in the **${verdict}** band for a ${claimedMw} MW asset. ` +
                `The strongest signal is ${strengthClause}; the binding constraint is ${blockerClause}. ` +
                rec;
              lines.push('');
              lines.push(determination);
            }

            return {
              response: lines.join('\n'),
              isSiteAuditResponse: true,
              dossier
            };
          } catch (error: any) {
            console.error(' Chat: Site audit error:', error);
            return {
              response: `Site audit failed: ${error.message}`,
              isSiteAuditResponse: true,
              isError: true
            };
          }
        }

        //  FORECAST ROUTING
        // Route to /api/geoint/forecast when the Forecast module is selected
        // and a pin is dropped. Backend fans out across configured AI weather
        // providers (Aurora / Earth-2 FCN / MAI Weather) and returns an
        // ensemble dossier.
        if (selectedModule === 'forecast') {
          // Same map-center fallback as Site Intel: geocoded location pan
          // is treated as an implicit pin so the user doesn't have to
          // manually click after typing a place name.
          const centerLat = (currentMapCtx as any)?.bounds?.center_lat;
          const centerLng = (currentMapCtx as any)?.bounds?.center_lng;
          const lat = currentMapCtx?.vision_pin?.lat || currentPin?.lat
            || (Number.isFinite(centerLat) ? centerLat : 0);
          const lng = currentMapCtx?.vision_pin?.lng || currentPin?.lng
            || (Number.isFinite(centerLng) ? centerLng : 0);

          if (lat === 0 && lng === 0) {
            return {
              response: [
                '**Forecast needs a pin.**',
                '',
                'Drop a pin on the map at the location you want forecast and resend your question.',
              ].join('\n'),
              isClarification: true,
            };
          }

          // Parse optional lead hours from the user query ("next 72 hours",
          // "10-day", "120h", etc.). Default 72h.
          let leadHours = 72;
          const m = (message || '').toLowerCase();
          const hMatch = m.match(/(\d+)\s*(?:h|hour|hours|hr|hrs)\b/);
          const dMatch = m.match(/(\d+)[-\s]*day/);
          if (hMatch) leadHours = Math.min(240, Math.max(1, parseInt(hMatch[1], 10)));
          else if (dMatch) leadHours = Math.min(240, Math.max(1, parseInt(dMatch[1], 10) * 24));

          console.log(' Chat: Routing to Forecast', { lat, lng, leadHours, query: message });

          try {
            const resp = await apiService.triggerForecast(
              lat,
              lng,
              message,
              { leadHours },
              controller.signal
            );
            const dossier = resp?.result || resp;
            console.log(' Chat: Forecast dossier:', dossier);

            const lines: string[] = [];
            const called: string[] = Array.isArray(dossier?.providers_called) ? dossier.providers_called : [];
            const succ: string[] = Array.isArray(dossier?.providers_succeeded) ? dossier.providers_succeeded : [];
            const failed: any[] = Array.isArray(dossier?.providers_failed) ? dossier.providers_failed : [];
            const summary = dossier?.ensemble_summary || {};
            const vars = summary?.variables || {};
            const note = dossier?.note || '';

            lines.push(`**AI weather ensemble** · ${lat.toFixed(3)}°, ${lng.toFixed(3)}° · +${leadHours}h`);
            if (succ.length > 0) {
              lines.push(`- Models run: ${succ.join(', ')}`);
            } else if (called.length > 0) {
              lines.push(`- Models attempted: ${called.join(', ')}`);
            }
            if (failed.length > 0) {
              lines.push(`- Models failed: ${failed.map((f: any) => `${f?.provider_id || f?.provider || '?'} (${f?.error || 'error'})`).join('; ')}`);
            }

            const varKeys = Object.keys(vars);
            if (varKeys.length > 0) {
              lines.push('');
              lines.push('**Ensemble (center cell)**');
              for (const v of varKeys) {
                const e = vars[v] || {};
                const mean = typeof e.mean === 'number' ? e.mean.toFixed(2) : '—';
                const spread = typeof e.spread === 'number' ? ` · spread ${e.spread.toFixed(2)}` : '';
                const stdev = typeof e.stdev === 'number' ? ` · σ ${e.stdev.toFixed(2)}` : '';
                const samples = typeof e.samples === 'number' ? ` · n=${e.samples}` : '';
                lines.push(`- \`${v}\` · mean ${mean}${spread}${stdev}${samples}`);
              }
            }

            if (note) {
              lines.push('');
              lines.push(`> _${note}_`);
            }

            return {
              response: lines.join('\n'),
              dossier,
            };
          } catch (error: any) {
            console.error(' Chat: Forecast error:', error);
            return {
              response: `Forecast failed: ${error.message}`,
              isError: true,
            };
          }
        }

        // Note: GEOINT analysis is now handled by MapView when a pin is dropped
        // Chat only handles normal conversational flow
        
        // Normal chat flow
        // Use working Enhanced PC Tools directly
        // This uses /chat endpoint which has the working satellite data search
        // Pass the conversation ID and message history for context
        // CRITICAL: Use mapContextRef.current to get the LATEST map state.
        // The closure-captured `mapContext` prop can be stale after navigate_to
        // because React state propagation (MapView -> MainApp -> Chat) takes
        // multiple render cycles. The ref is updated synchronously via useEffect.
        const freshMapContext = mapContextRef.current;
        console.log(` Chat: Sending message with ${currentPin ? 'pin' : 'no pin'}:`, currentPin);
        console.log(` Chat: GEOINT mode is ${geointMode ? 'ON' : 'OFF'}`);
        console.log(` Chat: Map context for vision (from ref):`, {
          has_satellite_data: freshMapContext?.has_satellite_data,
          has_screenshot: !!freshMapContext?.imagery_base64,
          collection: freshMapContext?.current_collection,
          tile_urls_count: freshMapContext?.tile_urls?.length || 0,
          vision_mode: freshMapContext?.vision_mode,
          vision_pin: freshMapContext?.vision_pin,
          bounds: freshMapContext?.bounds
        });
        const result = await apiService.sendChatMessage(message, selectedDataset?.id, conversationId, messages, currentPin || undefined, geointMode, freshMapContext, selectedModel, false, stacMode, controller.signal);

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
      // If the user clicked Stop while this turn was in flight, drop the
      // response on the floor — the Thinking message was already removed
      // by handleStopMessage, and we don't want a late reply to surprise
      // the user.
      if (cancelledRef.current) {
        console.log(' Chat: Ignoring chatMutation.onSuccess — turn was cancelled by user');
        cancelledRef.current = false;
        return;
      }
      // Check if this is a GEOINT analysis result
      if (responseData?.geoint_result) {
        console.log(' Chat: GEOINT analysis result received');
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
      
      //  COMPARISON RESPONSE HANDLING
      if (responseData?.isComparisonResponse) {
        console.log(' Chat: Comparison analysis result received');
        
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
      
      //  BUILDING DAMAGE RESPONSE HANDLING
      if (responseData?.isBuildingDamageResponse) {
        console.log(' Chat: Building damage analysis result received');
        
        setMessages(prev => ([
          ...prev,
          {
            role: 'assistant',
            content: responseData.response,
            timestamp: new Date()
          }
        ]));
        
        return;
      }
      
      //  EXTREME WEATHER RESPONSE HANDLING
      if (responseData?.isExtremeWeatherResponse) {
        console.log(' Chat: Extreme weather analysis result received');
        console.log(' Chat: Display content length:', responseData.response?.length);
        console.log(' Chat: Display content preview:', responseData.response?.substring(0, 300));
        
        setMessages(prev => ([
          ...prev,
          {
            role: 'assistant',
            content: responseData.response,
            timestamp: new Date()
          }
        ]));
        
        return;
      }

      // ────────────────────────────────────────────────────────────
      // SEQUENTIAL PARTS HANDLER
      // The backend's QuerySplitter detected a multi-part question and
      // returned an intro + an array of self-contained sub-questions.
      // We render the intro bubble immediately, then dispatch each part
      // as its own /api/query call (with `partOfSplit=true` so the
      // splitter doesn't recurse). Dependent parts get the prior part's
      // answer prepended as context.
      //
      // Each sub-call is a normal turn → fast, never times out, and
      // flows through the existing clarifier so any ambiguous part
      // still triggers the usual follow-up question UX.
      // ────────────────────────────────────────────────────────────
      if (responseData?.action === 'sequential_parts' && Array.isArray(responseData?.parts)) {
        console.log(' Chat: Sequential parts plan received:', responseData.parts);

        // 1) Render the intro bubble.
        const introText = responseData.response || responseData.user_response ||
          `I'll answer this in ${responseData.parts.length} parts.`;
        setMessages(prev => ([
          ...prev,
          { role: 'assistant', content: introText, timestamp: new Date() },
        ]));

        // 2) Dispatch parts sequentially in a fire-and-forget async block.
        const sharedSessionId = responseData.session_id || conversationId;
        const partsList: Array<{ id: number; query: string; depends_on: number[] }> =
          responseData.parts;
        const freshMapCtxForParts = mapContextRef.current;

        (async () => {
          const answers: Record<number, string> = {};
          for (const part of partsList) {
            // For dependent parts, prepend a compact context block so the
            // backend agent has the prior answer available without needing
            // a fresh tool call.
            let queryText = part.query;
            if (part.depends_on && part.depends_on.length > 0) {
              const ctxLines = part.depends_on
                .map((d) => answers[d] ? `Part ${d} answer:\n${answers[d]}` : '')
                .filter(Boolean);
              if (ctxLines.length > 0) {
                queryText = `[Context from earlier parts]\n${ctxLines.join('\n\n')}\n\n[Now answer]\n${part.query}`;
              }
            }

            // Show a "Working on part N of M…" thinking bubble.
            setMessages(prev => ([
              ...prev,
              {
                role: 'assistant',
                content: `Working on part ${part.id} of ${partsList.length}…`,
                timestamp: new Date(),
                isThinking: true,
              },
            ]));

            try {
              const partResult = await apiService.sendChatMessage(
                queryText,
                selectedDataset?.id,
                sharedSessionId,
                messages,
                currentPin || undefined,
                geointMode,
                freshMapCtxForParts,
                selectedModel,
                true, // partOfSplit — prevents recursive splitting
                stacMode,
                controller.signal,
              );

              const partText =
                partResult?.response ||
                partResult?.user_response ||
                partResult?.message ||
                'No response received for this part.';
              answers[part.id] = typeof partText === 'string' ? partText : String(partText);

              // Replace the trailing thinking bubble with the actual answer.
              setMessages(prev => {
                const filtered = prev.filter((m, idx) => !(idx === prev.length - 1 && m.isThinking));
                return [
                  ...filtered,
                  {
                    role: 'assistant',
                    content: answers[part.id],
                    timestamp: new Date(),
                  },
                ];
              });

              if (onResponseReceived) {
                onResponseReceived(partResult);
              }
            } catch (err: any) {
              console.error(' Chat: Sequential part failed:', err);
              setMessages(prev => {
                const filtered = prev.filter((m, idx) => !(idx === prev.length - 1 && m.isThinking));
                return [
                  ...filtered,
                  {
                    role: 'assistant',
                    content: `Part ${part.id} failed: ${err?.message || 'unknown error'}. Continuing with remaining parts.`,
                    timestamp: new Date(),
                  },
                ];
              });
            }
          }
        })();

        return;
      }
      
      // Normal chat response handling
      // responseData is normalized to workflow result when using /query or /enhanced-chat
      console.log(' CHAT.TSX onSuccess FIRED! ');
      console.log(' Chat: Complete responseData received:', responseData);
      console.log(' Chat: responseData type:', typeof responseData);
      console.log(' Chat: responseData.response:', responseData?.response);
      console.log(' Chat: responseData.user_response:', responseData?.user_response);
      console.log(' Chat: responseData.message:', responseData?.message);

      // Handle case where responseData is already a string (e.g., from vision agent)
      let rawResponse: string;
      if (typeof responseData === 'string') {
        rawResponse = responseData;
        console.log(' Chat: responseData is string, using directly');
      } else {
        // Try multiple fields for response content
        rawResponse = responseData?.response || responseData?.user_response || responseData?.message || 'No response received';
        console.log(' Chat: Extracted rawResponse from object properties');
      }
      const textResponse = extractTextFromResponse(rawResponse);

      console.log(' Chat: Raw response:', rawResponse);
      console.log(' Chat: Extracted textResponse:', textResponse);
      console.log(' Chat: textResponse length:', textResponse?.length);

      // Source-chip metadata: harvest provenance fields the backend now
      // surfaces (data_source, tools_used) for chip rendering.
      const _dataSource = (typeof responseData === 'object' && responseData)
        ? responseData?.data_source
        : undefined;
      // Count of STAC items the backend search returned for this turn.
      // The backend exposes this in a few shapes depending on the
      // pipeline branch; we accept whichever is present so the chip can
      // show e.g. "Data: MPC Pro · 0 tiles" (instant verification that
      // the Pro toggle actually ran and what it produced).
      let _tilesAvailable: number | undefined;
      if (typeof responseData === 'object' && responseData) {
        const meta = responseData?.search_metadata;
        if (meta && typeof meta === 'object') {
          if (typeof meta.total_selected === 'number') _tilesAvailable = meta.total_selected;
          else if (typeof meta.total_found === 'number') _tilesAvailable = meta.total_found;
        }
        if (_tilesAvailable === undefined) {
          const feats = responseData?.results?.features;
          if (Array.isArray(feats)) _tilesAvailable = feats.length;
        }
      }
      const _toolsUsed = (typeof responseData === 'object' && responseData && Array.isArray(responseData?.tools_used))
        ? responseData.tools_used as string[]
        : undefined;
      // Authoritative routing decision the backend just made for this
      // turn. Surfaced in the SourceChips tooltip so the user can verify
      // Pro vs Public without depending on Log Analytics ingestion.
      const _stacRouting = (typeof responseData === 'object' && responseData)
        ? responseData?.debug?.stac_routing
        : undefined;
      // MCP tool-trace rows captured during the resilience SSE stream
      // (or any other streamed planner turn that emits them via the
      // mutationFn). When present, the message bubble will render a
      // <TraceDrawer> beneath it.
      const _toolTrace = (typeof responseData === 'object' && responseData && Array.isArray((responseData as any).toolTrace))
        ? (responseData as any).toolTrace
        : undefined;

      setMessages(prev => ([
        ...prev,
        {
          role: 'assistant',
          content: textResponse,
          timestamp: new Date(),
          dataSource: _dataSource,
          tilesAvailable: _tilesAvailable,
          toolsUsed: _toolsUsed,
          stacRouting: _stacRouting,
          toolTrace: _toolTrace,
        }
      ]));

      // Pass the complete response data to map for visualization
      console.log(' Chat: Passing response data to map:', JSON.stringify(responseData, null, 2));
      console.log(' Chat: Response data type:', typeof responseData);
      console.log(' Chat: Response data keys:', Object.keys(responseData || {}));

      // Pass the response data directly to the map without any hardcoded fallbacks
      const enhancedResponseData = responseData;

      if (onResponseReceived) {
        onResponseReceived(enhancedResponseData);
      }
    },
    onError: (error) => {
      // Same short-circuit as onSuccess — don't surface an error toast
      // for a turn the user explicitly cancelled.
      if (cancelledRef.current || (error as any)?.cancelled || (error as any)?.name === 'CanceledError') {
        console.log(' Chat: Ignoring chatMutation.onError — turn was cancelled by user');
        cancelledRef.current = false;
        return;
      }
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
        console.log(' Using direct VEDA search service:', { query, collection_id });
        const result = await vedaSearchService.search(query, collection_id);
        return result;
      } catch (error) {
        console.error('VEDA search error:', error);
        throw new Error('Failed to search VEDA datasets. Please check your configuration and try again.');
      }
    },
    onSuccess: (responseData) => {
      console.log(' VEDA Search: Complete responseData received:', responseData);

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
      console.log(' Chat: Processing pending query:', pendingQuery);
      
      // Capture the query and clear immediately to prevent re-triggering
      const queryToProcess = pendingQuery;
      setPendingQuery(null);
      
      // Set the input value
      setInputValue(queryToProcess);
      
      // Add user message
      const userMessage: ChatMessage = {
        role: 'user',
        content: queryToProcess,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, userMessage]);
      
      // Send the message using the chat mutation
      chatMutation.mutate(queryToProcess);
      
      // Clear input
      setInputValue('');
    }
  }, [pendingQuery]); // Remove chatMutation from dependencies to prevent re-triggering

  // Handle private search triggers from sidebar (Updated to use main chat endpoint)
  useEffect(() => {
    if (privateSearchTrigger && privateSearchTrigger.isPrivateQuery) {
      console.log(' Chat: Handling private search trigger:', privateSearchTrigger);
      
      const query = privateSearchTrigger.query;
      const collection_id = privateSearchTrigger.collection?.id;
      const collectionTitle = privateSearchTrigger.collection?.title || 'Dataset';
      
      // Clear previous chat and start fresh session
      const systemMessage: ChatMessage = {
        role: 'assistant',
        content: `**Copilot Search Mode**\n\nI'll search for Earth Science data using our semantic translator and STAC catalog integration.\n\n**Query Context:** ${collectionTitle}\n\nLet me process your request...`,
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
      console.log(' Chat: Handling PC structured search trigger:', privateSearchTrigger);

      const params = privateSearchTrigger.pcSearchParams;

      // Compose a precise LOAD-style natural-language query from the
      // structured params. We quote the collection ID so LoadAgent extracts
      // it verbatim (no LLM remapping). stacMode is read from the panel and
      // propagated to the backend via the existing sendChatMessage path —
      // same pipeline as a chat-driven LOAD, same map render, same chat
      // response shape. This intentionally avoids a separate /pc/search
      // endpoint so there's exactly one code path for "find STAC items".
      let nl = `Load collection "${params.collection}" over ${params.location}`;
      if (params.datetime) {
        nl += ` on ${params.datetime}`;
      } else if (params.datetime_start && params.datetime_end) {
        nl += ` from ${params.datetime_start} to ${params.datetime_end}`;
      }

      // Display string for the chat bubble (human-friendly form of `nl`).
      let displayQuery = `Searching ${params.collection} for ${params.location}`;
      if (params.datetime) {
        displayQuery += ` on ${params.datetime}`;
      } else if (params.datetime_start && params.datetime_end) {
        displayQuery += ` from ${params.datetime_start} to ${params.datetime_end}`;
      }

      const userMessage: ChatMessage = {
        role: 'user',
        content: displayQuery,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, userMessage]);

      // Honor the panel's stacMode for THIS turn — temporarily override the
      // ambient stacMode prop via a one-shot since `sendChatMessage` reads
      // `stacMode` from chatMutation's closure. The simplest correct thing
      // is to call sendChatMessage directly with the panel's mode, then
      // hand the result to the same onSuccess handler chatMutation uses.
      chatMutation.mutate(nl);
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

    // ----------------------------------------------------------------------
    // Demo-flow auto-soft-reset: when the user clearly starts a NEW search
    // (navigation/load verb + explicit place name), clear lingering Layer-2
    // module sessions so Layer-1 LOAD isn't shadowed by a leftover route.
    // The backend has a matching pin-override pre-check in translate_query.
    // ----------------------------------------------------------------------
    const _hasNavVerb =
      /^(?:show|find|display|map|imagery of|elevation map of|elevation of|navigate to|go to|take me to|fly to|zoom to|locate|search for)\b/i.test(
        inputValue.trim()
      );
    const _hasExplicitPlace =
      /[A-Z][a-zA-Z]+,\s*[A-Z][a-zA-Z]+/.test(inputValue) ||
      /\b[A-Z][a-zA-Z]+\s+[A-Z][a-zA-Z]+\b/.test(inputValue) ||
      /\b(?:of|in|over|at|near|around)\s+[A-Z][a-zA-Z]+/.test(inputValue);
    if (_hasNavVerb && _hasExplicitPlace) {
      console.log(' Chat: New-search detected — clearing module sessions');
      try { onClearVisionSession?.(); } catch (e) { /* noop */ }
      try { onClearTerrainSession?.(); } catch (e) { /* noop */ }
    }

    // Check if parent wants to intercept this message (e.g., for comparison query)
    if (onUserMessage && onUserMessage(inputValue)) {
      console.log(' Chat: Message intercepted by parent');
      setInputValue('');
      return;
    }
    
    // Use main chat endpoint instead of VEDA search (VEDA integration disabled)
    console.log(' Chat: Sending message via main chat endpoint:', { inputValue, selectedDataset: selectedDataset?.id });
    chatMutation.mutate(inputValue);
    
    setInputValue('');
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Stop / cancel the in-flight chat turn. Aborts the underlying HTTP
  // request via AbortController, removes the "Thinking..." UI
  // immediately, and tells onSuccess/onError to ignore the eventual
  // reply (in case the cancel raced with the response).
  const handleStopMessage = () => {
    console.log(' Chat: User requested STOP of in-flight turn');
    cancelledRef.current = true;
    // End-to-end cancel: abort the in-flight axios request so the
    // backend connection drops. The next user query starts cleanly.
    try {
      chatAbortRef.current?.abort();
    } catch (e) {
      console.warn(' Chat: abort() threw (non-fatal):', e);
    }
    chatAbortRef.current = null;
    // Drop any pending "Thinking..." bubbles so the chat returns to a
    // clean state. Same filter used by mobility/geoint cancel paths.
    setMessages(prev => prev.filter(msg => !msg.isThinking));
    chatMutation.reset();
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
          <span>Planetary Explorer Agent</span>
        </div>

        <div className="messages">
          {/* Examples removed to prevent flash on page load */}

          {pendingConfirms.length > 0 && (
            <div className="row assistant" aria-live="assertive">
              <div className="message-wrapper" style={{ width: '100%' }}>
                {pendingConfirms.map((p) => (
                  <ConfirmationCard
                    key={p.traceId}
                    pending={p}
                    onResolved={handleConfirmResolved}
                  />
                ))}
              </div>
            </div>
          )}

          {messages.map((message, index) => (
            <div key={index} className={`row ${message.role}`}>
              <div className="message-wrapper">
                {message.isThinking ? (
                  <div className="msg">
                    <div className="loading-indicator">
                      <span></span>
                      <span>Thinking...</span>
                    </div>
                  </div>
                ) : (
                  <div className="msg" dangerouslySetInnerHTML={{
                    __html: renderMessageHTML(message.content)
                  }}></div>
                )}
                {message.role === 'assistant' && !message.isThinking && (
                  <SourceChips
                    dataSource={message.dataSource}
                    tilesAvailable={message.tilesAvailable}
                    toolsUsed={message.toolsUsed}
                    stacRouting={message.stacRouting}
                  />
                )}
                {message.role === 'assistant' && !message.isThinking && Array.isArray(message.toolTrace) && message.toolTrace.length > 0 && (
                  <TraceDrawer rows={message.toolTrace as any} inline />
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
                  : terrainSession && (terrainSession.sessionId || selectedModule === 'terrain')
                  ? "Ask a follow-up question about this terrain..."
                  : selectedModule === 'extreme_weather'
                  ? "Ask about climate projections, temperature trends, extreme heat days..."
                  : selectedModule === 'site_audit'
                  ? "Ask about this candidate site (e.g., 'Audit a 200 MW data center here')..."
                  : isVedaMode 
                  ? "Ask about climate data, earth observations, or environmental datasets..."
                  : selectedDataset
                  ? `Ask about ${selectedDataset.title}...`
                  : "Ask about Earth data..."
              }
              disabled={chatMutation.isPending}
            />
            {chatMutation.isPending ? (
              <button
                className="btn send"
                onClick={handleStopMessage}
                aria-label="Stop generating"
                title="Stop generating"
              >
                Stop
              </button>
            ) : (
              <button
                className={`btn send ${inputValue.trim() ? 'has-text' : ''}`}
                onClick={handleSendMessage}
                disabled={!inputValue.trim()}
              >
                Send
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Chat;
// Build trigger: 2026-01-06 15:04:47
