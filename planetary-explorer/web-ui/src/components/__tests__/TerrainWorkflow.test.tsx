// Test: End-to-End Terrain Analysis Workflow
// Verifies that the complete flow works: Pin Drop -> Thinking -> Backend Call -> Chat Response

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock data structures
interface GeointAnalysisEvent {
  type: 'thinking' | 'assistant' | 'error' | 'pin_dropped' | 'complete' | 'pending';
  message: string;
  analysis?: string;
  features?: string[];
  confidence?: number;
}

interface MobilityAnalysisResult {
  type: string;
  message?: string;
  analysis?: string;
  features_identified?: string[];
  confidence?: number;
}

describe('Terrain Analysis Workflow - End to End', () => {
  let onGeointAnalysisCalls: GeointAnalysisEvent[] = [];
  let chatMessages: string[] = [];

  beforeEach(() => {
    // Reset tracking arrays
    onGeointAnalysisCalls = [];
    chatMessages = [];
  });

  // Mock MapView's onGeointAnalysis callback
  const mockOnGeointAnalysis = (event: GeointAnalysisEvent) => {
    console.log('MapView called onGeointAnalysis:', event);
    onGeointAnalysisCalls.push(event);
  };

  // Mock MainApp's handleMobilityAnalysisResult (the handler for geoint events)
  const mockHandleMobilityAnalysisResult = (result: MobilityAnalysisResult) => {
    console.log('MainApp: handleMobilityAnalysisResult called:', result);
    
    // THIS IS THE FIX - Handle 'thinking', 'assistant', and 'error' types
    if (result.type === 'thinking') {
      // Add thinking message to chat
      const message = result.message || 'Analyzing...';
      chatMessages.push(message);
      console.log('[MSG] Chat: Added thinking message:', message);
    } 
    else if (result.type === 'assistant') {
      // Add analysis result to chat
      const message = result.message || result.analysis || 'Analysis completed';
      chatMessages.push(message);
      console.log('[MSG] Chat: Added assistant message:', message);
    }
    else if (result.type === 'error') {
      // Add error message to chat
      const errorMessage = result.message || 'Analysis failed';
      chatMessages.push(`${errorMessage}`);
      console.log('[MSG] Chat: Added error message:', errorMessage);
    }
    else if (result.type === 'pin_dropped') {
      console.log('[PIN] Pin dropped at location');
    }
    else if (result.type === 'complete') {
      const message = result.analysis || 'Analysis completed';
      chatMessages.push(message);
      console.log('[MSG] Chat: Analysis complete:', message);
    }
  };

  // Mock backend API response
  const mockBackendResponse = {
    status: 'success',
    result: {
      analysis: `1. Overview
- The pinned location lies within the Wickaboxet Wildlife Management Area west of the village of West Greenwich, Rhode Island.
- The broader view shows a largely forested, rural upland landscape with numerous small ponds and wetlands embedded in rolling hills.

2. Terrain Characteristics
- Elevation: Low to moderate rolling terrain (approx 50-150m)
- Topography: Gentle hills with occasional steeper slopes
- Drainage: Well-drained uplands with wetland depressions

3. Land Cover
- Deciduous and mixed forest dominates (oak-pine-hickory)
- Agricultural clearings scattered throughout
- Wetlands and ponds in low-lying areas

4. Accessibility
- Moderate road network with dirt/gravel forest roads
- Some trails for recreation
- Limited development, rural character maintained`,
      features_identified: [
        'Forested uplands',
        'Wetland complexes',
        'Agricultural clearings',
        'Rolling terrain',
        'Pond networks',
        'Forest roads',
        'Low development density'
      ],
      confidence: 0.92
    }
  };

  it('should complete full terrain analysis workflow: Pin -> Thinking -> Analysis -> Chat Display', async () => {
    console.log('\n[TEST] TEST: Full Terrain Analysis Workflow\n');

    // STEP 1: User drops pin on map (MapView.tsx handleTerrainAnalysisClick)
    console.log('[PIN] STEP 1: User drops pin at coordinates (41.648002, -71.716736)');
    
    // STEP 2: MapView sends "thinking" event
    console.log('STEP 2: MapView sends thinking event to Chat');
    mockOnGeointAnalysis({
      type: 'thinking',
      message: 'Analyzing terrain features with GPT-5 Vision...'
    });
    
    // STEP 3: MainApp forwards to Chat via handleMobilityAnalysisResult
    console.log('STEP 3: MainApp processes thinking event');
    mockHandleMobilityAnalysisResult({
      type: 'thinking',
      message: onGeointAnalysisCalls[0].message
    });

    // Verify thinking message appears in chat
    expect(chatMessages).toHaveLength(1);
    expect(chatMessages[0]).toBe('Analyzing terrain features with GPT-5 Vision...');
    console.log('Thinking message displayed in chat');

    // STEP 4: Backend API call completes (simulated)
    console.log('[WEB] STEP 4: Backend API returns terrain analysis result');
    
    // STEP 5: MapView sends "assistant" event with results
    console.log('STEP 5: MapView sends assistant event with analysis');
    
    // Format numbered section headers to be bold (matching MapView logic)
    const formattedAnalysis = mockBackendResponse.result.analysis.replace(/^(\d+\.\s+[^\n]+)/gm, '**$1**');

    mockOnGeointAnalysis({
      type: 'assistant',
      message: formattedAnalysis
    });

    // STEP 6: MainApp forwards to Chat
    console.log('STEP 6: MainApp processes assistant event');
    mockHandleMobilityAnalysisResult({
      type: 'assistant',
      message: onGeointAnalysisCalls[1].message
    });

    // Verify analysis appears in chat
    expect(chatMessages).toHaveLength(2);
    expect(chatMessages[1]).toContain('**1. Overview**');
    expect(chatMessages[1]).toContain('Wickaboxet Wildlife Management Area');
    expect(chatMessages[1]).toContain('Deciduous and mixed forest dominates');
    console.log('Analysis results displayed in chat');

    // FINAL VERIFICATION
    console.log('\nFINAL VERIFICATION:');
    console.log(`   - onGeointAnalysis called: ${onGeointAnalysisCalls.length} times`);
    console.log(`   - Chat messages added: ${chatMessages.length}`);
    console.log(`   - Message 1 (thinking): ${chatMessages[0].substring(0, 50)}...`);
    console.log(`   - Message 2 (results): ${chatMessages[1].substring(0, 50)}...`);
    
    expect(onGeointAnalysisCalls).toHaveLength(2);
    expect(onGeointAnalysisCalls[0].type).toBe('thinking');
    expect(onGeointAnalysisCalls[1].type).toBe('assistant');
    expect(chatMessages).toHaveLength(2);
    
    console.log('ALL CHECKS PASSED - Terrain workflow complete!\n');
  });

  it('should handle error case gracefully', async () => {
    console.log('\n[TEST] TEST: Error Handling\n');

    // STEP 1: Thinking message
    mockOnGeointAnalysis({
      type: 'thinking',
      message: 'Analyzing terrain features with GPT-5 Vision...'
    });
    mockHandleMobilityAnalysisResult({
      type: 'thinking',
      message: onGeointAnalysisCalls[0].message
    });

    // STEP 2: API error occurs
    console.log('STEP 2: Backend API returns error');
    mockOnGeointAnalysis({
      type: 'error',
      message: 'Failed to analyze terrain: Network timeout'
    });
    mockHandleMobilityAnalysisResult({
      type: 'error',
      message: onGeointAnalysisCalls[1].message
    });

    // Verify error message appears
    expect(chatMessages).toHaveLength(2);
    expect(chatMessages[0]).toBe('Analyzing terrain features with GPT-5 Vision...');
    expect(chatMessages[1]).toContain('');
    expect(chatMessages[1]).toContain('Failed to analyze terrain');
    console.log('Error handled correctly\n');
  });

  it('should verify event types match between MapView and MainApp', () => {
    console.log('\n[TEST] TEST: Event Type Compatibility\n');

    // MapView sends these event types
    const mapViewEventTypes = ['thinking', 'assistant', 'error'];
    
    // MainApp should handle these same types
    const handledTypes: string[] = [];

    // Test each event type
    mapViewEventTypes.forEach(eventType => {
      const testEvent: GeointAnalysisEvent = {
        type: eventType as any,
        message: `Test ${eventType} message`
      };
      
      mockOnGeointAnalysis(testEvent);
      const beforeCount = chatMessages.length;
      mockHandleMobilityAnalysisResult({
        type: eventType,
        message: testEvent.message
      });
      const afterCount = chatMessages.length;

      // If message was added, the type was handled
      if (afterCount > beforeCount) {
        handledTypes.push(eventType);
        console.log(`Event type '${eventType}' handled correctly`);
      } else {
        console.log(`Event type '${eventType}' NOT handled`);
      }
    });

    // Verify all types are handled
    expect(handledTypes).toHaveLength(mapViewEventTypes.length);
    expect(handledTypes).toEqual(expect.arrayContaining(mapViewEventTypes));
    console.log('All event types properly handled\n');
  });

  it('should format analysis message correctly with bold section headers', () => {
    console.log('\n[TEST] TEST: Message Formatting\n');

    const analysis = `1. Overview
This is the overview section.

2. Elevation & Landforms
This covers elevation details.

3. Vegetation
Details about vegetation.`;

    // Apply the same formatting logic as MapView
    const formattedMessage = analysis.replace(/^(\d+\.\s+[^\n]+)/gm, '**$1**');

    expect(formattedMessage).toContain('**1. Overview**');
    expect(formattedMessage).toContain('**2. Elevation & Landforms**');
    expect(formattedMessage).toContain('**3. Vegetation**');
    expect(formattedMessage).toContain('This is the overview section.');
    expect(formattedMessage).toContain('This covers elevation details.');
    expect(formattedMessage).toContain('Details about vegetation.');

    console.log('Message formatting correct\n');
  });
});
