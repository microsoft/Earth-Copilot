import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import MapView from '../MapView';
import Chat from '../Chat';
import MainApp from '../MainApp';

/**
 * Comprehensive End-to-End Tests for GEOINT Modules Flow
 * 
 * Tests the complete user journey:
 * 1. User clicks pin button
 * 2. Modules menu appears (if no module selected)
 * 3. User selects a module (terrain/mobility/building_damage)
 * 4. Chat receives "module selected" notification
 * 5. User clicks pin button again to enable pin mode
 * 6. Pin button turns green
 * 7. Chat receives "pin mode activated" notification
 * 8. User clicks on map to drop pin
 * 9. Pin marker appears on map
 * 10. Chat receives "pin dropped" notification
 * 11. GEOINT analysis is triggered automatically
 * 12. Chat receives "pending" notification (thinking...)
 * 13. Chat receives "complete" notification with results
 */

// Mock Azure Maps SDK
const mockAzureMaps = {
  Map: vi.fn().mockImplementation(() => ({
    events: {
      add: vi.fn(),
      remove: vi.fn()
    },
    markers: {
      add: vi.fn(),
      remove: vi.fn()
    },
    setCamera: vi.fn(),
    sources: {
      add: vi.fn(),
      remove: vi.fn(),
      getById: vi.fn()
    },
    layers: {
      add: vi.fn(),
      remove: vi.fn()
    }
  })),
  HtmlMarker: vi.fn().mockImplementation((options) => ({
    options,
    setOptions: vi.fn()
  })),
  data: {
    Position: vi.fn((lng, lat) => [lng, lat])
  }
};

// Mock Leaflet
const mockLeaflet = {
  map: vi.fn().mockReturnValue({
    on: vi.fn(),
    off: vi.fn(),
    setView: vi.fn(),
    addLayer: vi.fn(),
    removeLayer: vi.fn()
  }),
  marker: vi.fn().mockReturnValue({
    addTo: vi.fn().mockReturnThis(),
    bindPopup: vi.fn().mockReturnThis(),
    openPopup: vi.fn().mockReturnThis()
  }),
  icon: vi.fn().mockReturnValue({})
};

// Mock API service
const mockApiService = {
  triggerGeointAnalysis: vi.fn().mockResolvedValue({
    result: {
      analysis: 'Test terrain analysis result',
      features_identified: ['hills', 'valleys', 'water'],
      imagery_metadata: {
        source: 'Sentinel-2',
        date: '2025-10-21'
      }
    }
  })
};

describe('GEOINT Modules End-to-End Flow', () => {
  beforeEach(() => {
    // Setup global mocks
    (global as any).atlas = mockAzureMaps;
    (global as any).L = mockLeaflet;
    
    // Clear all mocks
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Module Selection Flow', () => {
    it('should show modules menu when pin button clicked without module selected', async () => {
      const onGeointAnalysis = vi.fn();
      
      const { container } = render(
        <MapView 
          onGeointAnalysis={onGeointAnalysis}
        />
      );

      // Find and click pin button
      const pinButton = container.querySelector('[title*="Select GEOINT Module"]');
      expect(pinButton).toBeInTheDocument();
      
      fireEvent.click(pinButton!);

      // Wait for modules menu to appear
      await waitFor(() => {
        const modulesMenu = screen.getByText(/Geointelligence Modules/i);
        expect(modulesMenu).toBeInTheDocument();
      });

      // Verify info message sent to chat
      expect(onGeointAnalysis).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'info',
          message: expect.stringContaining('select a geointelligence module')
        })
      );
    });

    it('should send "module_selected" notification when terrain module is selected', async () => {
      const onGeointAnalysis = vi.fn();
      
      const { container } = render(
        <MapView 
          onGeointAnalysis={onGeointAnalysis}
        />
      );

      // Open modules menu
      const pinButton = container.querySelector('[title*="Select GEOINT Module"]');
      fireEvent.click(pinButton!);

      // Select terrain module
      await waitFor(() => {
        const terrainButton = screen.getByText(/Terrain Analysis/i);
        fireEvent.click(terrainButton);
      });

      // Verify module selected notification
      expect(onGeointAnalysis).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'module_selected',
          message: expect.stringContaining('')
        })
      );
    });

    it('should send "module_selected" notification when mobility module is selected', async () => {
      const onGeointAnalysis = vi.fn();
      
      const { container } = render(
        <MapView 
          onGeointAnalysis={onGeointAnalysis}
        />
      );

      // Open modules menu
      const pinButton = container.querySelector('[title*="Select GEOINT Module"]');
      fireEvent.click(pinButton!);

      // Select mobility module
      await waitFor(() => {
        const mobilityButton = screen.getByText(/Mobility Analysis/i);
        fireEvent.click(mobilityButton);
      });

      // Verify module selected notification
      expect(onGeointAnalysis).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'module_selected',
          message: expect.stringContaining('[CAR]')
        })
      );
    });

    it('should send "module_selected" notification when building damage module is selected', async () => {
      const onGeointAnalysis = vi.fn();
      
      const { container } = render(
        <MapView 
          onGeointAnalysis={onGeointAnalysis}
        />
      );

      // Open modules menu
      const pinButton = container.querySelector('[title*="Select GEOINT Module"]');
      fireEvent.click(pinButton!);

      // Select building damage module
      await waitFor(() => {
        const buildingButton = screen.getByText(/Building Damage Analysis/i);
        fireEvent.click(buildingButton);
      });

      // Verify module selected notification
      expect(onGeointAnalysis).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'module_selected',
          message: expect.stringContaining('[BUILD]')
        })
      );
    });
  });

  describe('Pin Mode Activation Flow', () => {
    it('should enable pin mode and turn button green when pin clicked after module selection', async () => {
      const onGeointAnalysis = vi.fn();
      
      const { container } = render(
        <MapView 
          onGeointAnalysis={onGeointAnalysis}
        />
      );

      // Select a module first
      const pinButton = container.querySelector('[title*="Select GEOINT Module"]') as HTMLElement;
      fireEvent.click(pinButton);

      await waitFor(() => {
        const terrainButton = screen.getByText(/Terrain Analysis/i);
        fireEvent.click(terrainButton);
      });

      // Clear previous calls
      onGeointAnalysis.mockClear();

      // Click pin button again to enable pin mode
      await waitFor(() => {
        const enablePinButton = container.querySelector('[title*="Enable Pin Mode"]') as HTMLElement;
        expect(enablePinButton).toBeInTheDocument();
        fireEvent.click(enablePinButton);
      });

      // Verify pin mode activated notification
      expect(onGeointAnalysis).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'info',
          message: expect.stringContaining('[PIN]')
        })
      );

      // Verify button shows "Pin Mode: ON"
      await waitFor(() => {
        const activeButton = container.querySelector('[title*="Pin Mode: ON"]');
        expect(activeButton).toBeInTheDocument();
        
        // Check button has green background
        const buttonStyle = window.getComputedStyle(activeButton!);
        expect(buttonStyle.background).toContain('rgb(34, 197, 94)'); // Green color
      });
    });

    it('should NOT turn green when only module is selected but pin mode not activated', async () => {
      const { container } = render(
        <MapView />
      );

      // Select a module
      const pinButton = container.querySelector('[title*="Select GEOINT Module"]') as HTMLElement;
      fireEvent.click(pinButton);

      await waitFor(() => {
        const terrainButton = screen.getByText(/Terrain Analysis/i);
        fireEvent.click(terrainButton);
      });

      // Verify button does NOT have green background yet
      await waitFor(() => {
        const button = container.querySelector('[title*="Enable Pin Mode"]') as HTMLElement;
        expect(button).toBeInTheDocument();
        
        const buttonStyle = window.getComputedStyle(button);
        expect(buttonStyle.background).not.toContain('rgb(34, 197, 94)');
        expect(buttonStyle.background).toContain('rgba(255, 255, 255'); // White background
      });
    });
  });

  describe('Pin Placement Flow', () => {
    it('should place pin marker when map is clicked in pin mode', async () => {
      const onGeointAnalysis = vi.fn();
      const onPinChange = vi.fn();
      
      // Mock API import
      vi.mock('../../services/api', () => ({
        triggerGeointAnalysis: mockApiService.triggerGeointAnalysis
      }));

      const { container } = render(
        <MapView 
          onGeointAnalysis={onGeointAnalysis}
          onPinChange={onPinChange}
        />
      );

      // 1. Select module
      const pinButton = container.querySelector('[title*="Select GEOINT Module"]') as HTMLElement;
      fireEvent.click(pinButton);

      await waitFor(() => {
        const terrainButton = screen.getByText(/Terrain Analysis/i);
        fireEvent.click(terrainButton);
      });

      // 2. Enable pin mode
      await waitFor(() => {
        const enableButton = container.querySelector('[title*="Enable Pin Mode"]') as HTMLElement;
        fireEvent.click(enableButton);
      });

      // 3. Simulate map click
      const testLat = 40.7128;
      const testLng = -74.0060;

      // Get map instance and trigger click event
      const mapInstance = mockAzureMaps.Map.mock.results[0].value;
      const clickHandler = mapInstance.events.add.mock.calls.find(
        (call: any) => call[0] === 'click'
      )?.[1];

      if (clickHandler) {
        clickHandler({ position: [testLng, testLat] });
      }

      // 4. Verify pin marker was created
      await waitFor(() => {
        expect(mockAzureMaps.HtmlMarker).toHaveBeenCalled();
        expect(mapInstance.markers.add).toHaveBeenCalled();
      });

      // 5. Verify onPinChange callback
      expect(onPinChange).toHaveBeenCalledWith({
        lat: testLat,
        lng: testLng
      });

      // 6. Verify "pin_dropped" notification
      expect(onGeointAnalysis).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'pin_dropped',
          message: expect.stringContaining('[PIN]'),
          coordinates: { lat: testLat, lng: testLng }
        })
      );
    });

    it('should display pin coordinate indicator when pin is active', async () => {
      const { container } = render(
        <MapView />
      );

      // Place a pin (simulate the flow)
      const pinButton = container.querySelector('[title*="Select GEOINT Module"]') as HTMLElement;
      fireEvent.click(pinButton);

      await waitFor(() => {
        const terrainButton = screen.getByText(/Terrain Analysis/i);
        fireEvent.click(terrainButton);
      });

      await waitFor(() => {
        const enableButton = container.querySelector('[title*="Enable Pin Mode"]') as HTMLElement;
        fireEvent.click(enableButton);
      });

      // Simulate pin placement
      const mapInstance = mockAzureMaps.Map.mock.results[0].value;
      const clickHandler = mapInstance.events.add.mock.calls.find(
        (call: any) => call[0] === 'click'
      )?.[1];

      if (clickHandler) {
        clickHandler({ position: [-74.0060, 40.7128] });
      }

      // Verify pin coordinate indicator appears
      await waitFor(() => {
        const pinIndicator = container.querySelector('[title*="Pin Location"]');
        expect(pinIndicator).toBeInTheDocument();
      });
    });
  });

  describe('GEOINT Analysis Trigger Flow', () => {
    it('should automatically trigger terrain analysis when pin is dropped', async () => {
      const onGeointAnalysis = vi.fn();
      
      vi.mock('../../services/api', () => ({
        triggerGeointAnalysis: mockApiService.triggerGeointAnalysis
      }));

      const { container } = render(
        <MapView 
          onGeointAnalysis={onGeointAnalysis}
        />
      );

      // Complete the flow: select module -> enable pin mode -> drop pin
      const pinButton = container.querySelector('[title*="Select GEOINT Module"]') as HTMLElement;
      fireEvent.click(pinButton);

      await waitFor(() => {
        const terrainButton = screen.getByText(/Terrain Analysis/i);
        fireEvent.click(terrainButton);
      });

      await waitFor(() => {
        const enableButton = container.querySelector('[title*="Enable Pin Mode"]') as HTMLElement;
        fireEvent.click(enableButton);
      });

      // Drop pin
      const mapInstance = mockAzureMaps.Map.mock.results[0].value;
      const clickHandler = mapInstance.events.add.mock.calls.find(
        (call: any) => call[0] === 'click'
      )?.[1];

      if (clickHandler) {
        clickHandler({ position: [-74.0060, 40.7128] });
      }

      // Verify "pending" notification (thinking...)
      await waitFor(() => {
        expect(onGeointAnalysis).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'pending',
            message: expect.stringContaining('[THINK]')
          })
        );
      });

      // Verify API was called with correct parameters
      await waitFor(() => {
        expect(mockApiService.triggerGeointAnalysis).toHaveBeenCalledWith(
          40.7128,
          -74.0060,
          'terrain_analysis',
          expect.any(String),
          expect.any(String)
        );
      });

      // Verify "complete" notification with results
      await waitFor(() => {
        expect(onGeointAnalysis).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'complete',
            data: expect.objectContaining({
              result: expect.any(Object)
            })
          })
        );
      });
    });

    it('should trigger mobility analysis with correct API module name', async () => {
      const onGeointAnalysis = vi.fn();
      
      vi.mock('../../services/api', () => ({
        triggerGeointAnalysis: mockApiService.triggerGeointAnalysis
      }));

      const { container } = render(
        <MapView 
          onGeointAnalysis={onGeointAnalysis}
        />
      );

      // Select mobility module
      const pinButton = container.querySelector('[title*="Select GEOINT Module"]') as HTMLElement;
      fireEvent.click(pinButton);

      await waitFor(() => {
        const mobilityButton = screen.getByText(/Mobility Analysis/i);
        fireEvent.click(mobilityButton);
      });

      await waitFor(() => {
        const enableButton = container.querySelector('[title*="Enable Pin Mode"]') as HTMLElement;
        fireEvent.click(enableButton);
      });

      // Drop pin
      const mapInstance = mockAzureMaps.Map.mock.results[0].value;
      const clickHandler = mapInstance.events.add.mock.calls.find(
        (call: any) => call[0] === 'click'
      )?.[1];

      if (clickHandler) {
        clickHandler({ position: [-74.0060, 40.7128] });
      }

      // Verify API called with 'mobility_analysis'
      await waitFor(() => {
        expect(mockApiService.triggerGeointAnalysis).toHaveBeenCalledWith(
          40.7128,
          -74.0060,
          'mobility_analysis', // API module name
          expect.any(String),
          expect.any(String)
        );
      });
    });

    it('should trigger building damage analysis with correct API module name', async () => {
      const onGeointAnalysis = vi.fn();
      
      vi.mock('../../services/api', () => ({
        triggerGeointAnalysis: mockApiService.triggerGeointAnalysis
      }));

      const { container } = render(
        <MapView 
          onGeointAnalysis={onGeointAnalysis}
        />
      );

      // Select building damage module
      const pinButton = container.querySelector('[title*="Select GEOINT Module"]') as HTMLElement;
      fireEvent.click(pinButton);

      await waitFor(() => {
        const buildingButton = screen.getByText(/Building Damage Analysis/i);
        fireEvent.click(buildingButton);
      });

      await waitFor(() => {
        const enableButton = container.querySelector('[title*="Enable Pin Mode"]') as HTMLElement;
        fireEvent.click(enableButton);
      });

      // Drop pin
      const mapInstance = mockAzureMaps.Map.mock.results[0].value;
      const clickHandler = mapInstance.events.add.mock.calls.find(
        (call: any) => call[0] === 'click'
      )?.[1];

      if (clickHandler) {
        clickHandler({ position: [-74.0060, 40.7128] });
      }

      // Verify API called with 'building_damage'
      await waitFor(() => {
        expect(mockApiService.triggerGeointAnalysis).toHaveBeenCalledWith(
          40.7128,
          -74.0060,
          'building_damage', // API module name
          expect.any(String),
          expect.any(String)
        );
      });
    });
  });

  describe('Chat Integration Flow', () => {
    it('should display all GEOINT notifications in Chat component', async () => {
      const messages: any[] = [];
      const mockSetMessages = vi.fn((updater) => {
        const newMessages = typeof updater === 'function' ? updater(messages) : updater;
        messages.push(...newMessages);
      });

      // Mock useState for messages
      vi.spyOn(require('react'), 'useState')
        .mockImplementation((initial) => {
          if (Array.isArray(initial)) {
            return [messages, mockSetMessages];
          }
          return [initial, vi.fn()];
        });

      const mobilityAnalysisResults = [
        { type: 'info', message: 'Please select a geointelligence module to analyze.' },
        { type: 'module_selected', message: '**Terrain Analysis Selected**\n\nPlease drop a pin on the location to perform terrain analysis.' },
        { type: 'info', message: '[PIN] **Pin Mode Activated** - Click on the map to drop your pin.' },
        { type: 'pin_dropped', message: '[PIN] **Coordinates stored.**', coordinates: { lat: 40.7128, lng: -74.0060 } },
        { type: 'pending', message: '[THINK] **Thinking...**\n\nPerforming Terrain Analysis using GPT-5 Vision on satellite imagery.' },
        { 
          type: 'complete', 
          data: { 
            result: { 
              analysis: 'Test analysis result',
              features_identified: ['hills', 'valleys']
            } 
          } 
        }
      ];

      for (const result of mobilityAnalysisResults) {
        const { rerender } = render(
          <Chat 
            mobilityAnalysisResult={result}
            chatMode="geoint"
            selectedModule="terrain"
          />
        );

        await waitFor(() => {
          expect(mockSetMessages).toHaveBeenCalled();
        });

        mockSetMessages.mockClear();
      }

      // Verify all message types were processed
      expect(messages.length).toBeGreaterThan(0);
    });
  });

  describe('Error Handling', () => {
    it('should handle GEOINT analysis API failure gracefully', async () => {
      const onGeointAnalysis = vi.fn();
      
      // Mock API to fail
      const failingApiService = {
        triggerGeointAnalysis: vi.fn().mockRejectedValue(new Error('API connection failed'))
      };
      
      vi.mock('../../services/api', () => ({
        triggerGeointAnalysis: failingApiService.triggerGeointAnalysis
      }));

      const { container } = render(
        <MapView 
          onGeointAnalysis={onGeointAnalysis}
        />
      );

      // Complete flow to trigger analysis
      const pinButton = container.querySelector('[title*="Select GEOINT Module"]') as HTMLElement;
      fireEvent.click(pinButton);

      await waitFor(() => {
        const terrainButton = screen.getByText(/Terrain Analysis/i);
        fireEvent.click(terrainButton);
      });

      await waitFor(() => {
        const enableButton = container.querySelector('[title*="Enable Pin Mode"]') as HTMLElement;
        fireEvent.click(enableButton);
      });

      const mapInstance = mockAzureMaps.Map.mock.results[0].value;
      const clickHandler = mapInstance.events.add.mock.calls.find(
        (call: any) => call[0] === 'click'
      )?.[1];

      if (clickHandler) {
        clickHandler({ position: [-74.0060, 40.7128] });
      }

      // Verify error is handled and sent to chat
      await waitFor(() => {
        expect(onGeointAnalysis).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'complete',
            data: expect.objectContaining({
              result: expect.objectContaining({
                analysis: expect.stringContaining('failed')
              })
            })
          })
        );
      });
    });

    it('should NOT place pin if pin mode is not enabled', async () => {
      const onPinChange = vi.fn();
      
      const { container } = render(
        <MapView 
          onPinChange={onPinChange}
        />
      );

      // Try to click map without enabling pin mode
      const mapInstance = mockAzureMaps.Map.mock.results[0].value;
      const clickHandler = mapInstance.events.add.mock.calls.find(
        (call: any) => call[0] === 'click'
      )?.[1];

      if (clickHandler) {
        clickHandler({ position: [-74.0060, 40.7128] });
      }

      // Verify no pin was created
      await waitFor(() => {
        expect(mockAzureMaps.HtmlMarker).not.toHaveBeenCalled();
        expect(onPinChange).not.toHaveBeenCalled();
      }, { timeout: 1000 });
    });

    it('should NOT place pin if no module is selected', async () => {
      const onPinChange = vi.fn();
      
      const { container } = render(
        <MapView 
          onPinChange={onPinChange}
        />
      );

      // Enable pin mode without selecting module (this should not be possible in UI, but test the guard)
      const mapInstance = mockAzureMaps.Map.mock.results[0].value;
      const clickHandler = mapInstance.events.add.mock.calls.find(
        (call: any) => call[0] === 'click'
      )?.[1];

      if (clickHandler) {
        clickHandler({ position: [-74.0060, 40.7128] });
      }

      // Verify no pin was created
      await waitFor(() => {
        expect(mockAzureMaps.HtmlMarker).not.toHaveBeenCalled();
        expect(onPinChange).not.toHaveBeenCalled();
      }, { timeout: 1000 });
    });
  });

  describe('Visual Feedback', () => {
    it('should show different button states throughout the flow', async () => {
      const { container } = render(
        <MapView />
      );

      // State 1: No module selected
      let pinButton = container.querySelector('[title*="Select GEOINT Module"]') as HTMLElement;
      expect(pinButton).toBeInTheDocument();
      let style = window.getComputedStyle(pinButton);
      expect(style.background).toContain('rgba(255, 255, 255'); // White

      // State 2: Module selected, pin mode not enabled
      fireEvent.click(pinButton);
      await waitFor(() => {
        const terrainButton = screen.getByText(/Terrain Analysis/i);
        fireEvent.click(terrainButton);
      });

      pinButton = container.querySelector('[title*="Enable Pin Mode"]') as HTMLElement;
      style = window.getComputedStyle(pinButton);
      expect(style.background).toContain('rgba(255, 255, 255'); // Still white

      // State 3: Pin mode enabled
      fireEvent.click(pinButton);
      await waitFor(() => {
        pinButton = container.querySelector('[title*="Pin Mode: ON"]') as HTMLElement;
        expect(pinButton).toBeInTheDocument();
        style = window.getComputedStyle(pinButton);
        expect(style.background).toContain('rgb(34, 197, 94)'); // Green
      });
    });
  });
});

describe('Map Style Menu Integration', () => {
  it('should position Map Style button in bottom right corner near zoom controls', () => {
    const { container } = render(<MapView />);

    const mapStyleButton = container.querySelector('[title="Change Map Style"]') as HTMLElement;
    expect(mapStyleButton).toBeInTheDocument();

    const style = window.getComputedStyle(mapStyleButton);
    expect(style.position).toBe('absolute');
    expect(style.bottom).toBe('130px'); // Above zoom controls
    expect(style.right).toBe('10px');
  });

  it('should use consistent styling with other map controls', () => {
    const { container } = render(<MapView />);

    const mapStyleButton = container.querySelector('[title="Change Map Style"]') as HTMLElement;
    const style = window.getComputedStyle(mapStyleButton);

    // Check it matches zoom control styling
    expect(style.width).toBe('48px');
    expect(style.height).toBe('48px');
    expect(style.borderRadius).toBe('12px');
    expect(style.fontSize).toBe('24px');
  });

  it('should apply page-wide font family to Map Style dropdown', async () => {
    const { container } = render(<MapView />);

    const mapStyleButton = container.querySelector('[title="Change Map Style"]') as HTMLElement;
    fireEvent.click(mapStyleButton);

    await waitFor(() => {
      const dropdownHeader = screen.getByText('Map Styles');
      expect(dropdownHeader).toBeInTheDocument();

      const style = window.getComputedStyle(dropdownHeader);
      expect(style.fontFamily).toContain('Segoe UI');
    });
  });
});
