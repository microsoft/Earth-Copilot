# Earth Copilot Debugging Guide

## Overview
This guide provides comprehensive debugging setup for all Earth Copilot components:
- **React UI** (Port 5173) - Frontend interface
- **Router Function App** (Port 7071) - Natural language processing & Semantic Kernel
- **STAC Function App** (Port 7072) - Satellite data search & Microsoft Planetary Computer integration

## 🚀 Quick Start Debugging

### 1. **Start All Services for Debugging**
Use VSCode Command Palette (`Ctrl+Shift+P`) → "Tasks: Run Task" → "🚀 Debug Full Earth Copilot System"

OR manually start each service:

#### Option A: Debug Mode (with breakpoints)
1. **STAC Function**: Debug → "🔍 Debug STAC Function App (Port 7072)"
2. **Router Function**: Debug → "🌍 Debug Router Function App (Port 7071)"  
3. **React UI**: Terminal → `cd earth_copilot/react-ui && npm run dev`

#### Option B: Regular Mode
1. **Start STAC Function**: Run Task → "🔍 Start STAC Function (Port 7072)"
2. **Start Router Function**: Run Task → "🌍 Start Router Function (Port 7071)"
3. **Start React UI**: Run Task → "🚀 Start React UI (Port 5173)"

### 2. **Test the System**
- **Health Checks**: Run Tasks → "🧪 Test Router Function Health" + "🧪 Test STAC Function Health"
- **End-to-End Test**: Run Task → "🧪 Test End-to-End Query"
- **Open UI**: Navigate to http://localhost:5173

## 🔍 Component-Specific Debugging

### React UI Debugging (Port 5173)
```bash
cd earth_copilot/react-ui
npm run dev
```

**Debugging Features:**
- **Hot Reload**: Code changes reflect immediately
- **Browser DevTools**: F12 → Console/Network tabs
- **React DevTools**: Install browser extension for component inspection
- **Network Monitoring**: Watch API calls to router function

**Key Files to Debug:**
- `src/App.tsx` - Main application logic
- `src/components/Chat.tsx` - Chat interface & API calls
- `src/components/MapView.tsx` - Map rendering & STAC data visualization
- `src/services/api.ts` - API service calls

### Router Function App Debugging (Port 7071)

**Launch Configuration**: "🌍 Debug Router Function App (Port 7071)"

**Key Debugging Points:**
- **Query Endpoint**: `function_app.py:query_endpoint()` - Main entry point
- **Semantic Translator**: `semantic_translator.py:translate_query()` - Natural language processing
- **Entity Extraction**: `semantic_translator.py:extract_entities()` - AI-powered entity recognition
- **Location Resolution**: `semantic_translator.py:resolve_location_to_bbox()` - Geocoding

**Environment Variables Required:**
```bash
AZURE_OPENAI_ENDPOINT=your_endpoint
AZURE_OPENAI_API_KEY=your_key  
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4
```

**Debugging Tips:**
- Set breakpoints in `semantic_translator.py` line 902 (`translate_query` method)
- Monitor Azure OpenAI API calls and responses
- Check location resolution and bounding box calculation
- Verify collection selection logic

### STAC Function App Debugging (Port 7072)

**Launch Configuration**: "🔍 Debug STAC Function App (Port 7072)"

**Key Debugging Points:**
- **STAC Search**: `function_app.py:real_stac_search()` - Main search logic
- **Query Building**: `function_app.py:build_stac_query()` - STAC query construction
- **Collection Detection**: `function_app.py:detect_collections()` - Smart collection selection
- **API Integration**: Microsoft Planetary Computer API calls

**Debugging Tips:**
- Set breakpoints in `function_app.py` line 51 (`real_stac_search` method)
- Monitor Microsoft Planetary Computer API responses
- Check STAC query construction and validation
- Verify result enhancement and metadata addition

## 🧪 End-to-End Request Flow Debugging

### Trace a Complete Request:
1. **Frontend**: User enters query in React UI
2. **API Call**: `src/services/api.ts` → POST to `/api/query`
3. **Router Function**: `function_app.py:query_endpoint()` receives request
4. **Semantic Translation**: `semantic_translator.py:translate_query()` processes natural language
5. **STAC Call**: Router calls STAC function with structured parameters
6. **STAC Search**: `stac_search_function/function_app.py:real_stac_search()` queries Microsoft PC
7. **Response Chain**: Results flow back through Router → React UI → Map visualization

### Debug Each Step:
1. **Set breakpoints** at each layer
2. **Monitor network traffic** in browser DevTools
3. **Check logs** in integrated terminal for each function
4. **Verify data transformation** at each step

## 🛠 Debugging Tools & Techniques

### VSCode Features:
- **Breakpoints**: Click line numbers to set/remove
- **Variable Inspection**: Hover over variables during debugging
- **Call Stack**: View function call hierarchy
- **Watch Expressions**: Monitor specific variables
- **Debug Console**: Execute code in debugging context

### Logging Levels:
Both function apps configured for enhanced logging:
- **Debug**: Detailed execution flow
- **Info**: Key operations and results
- **Warning**: Non-critical issues
- **Error**: Failures and exceptions

### Network Debugging:
- **Browser DevTools**: Monitor React UI ↔ Router Function communication
- **Function Logs**: Monitor Router Function ↔ STAC Function communication
- **API Testing**: Use tasks to test endpoints directly

## 🚨 Common Issues & Solutions

### Port Conflicts:
**Problem**: "Port already in use"
**Solution**: Run Task → "🛑 Kill All Services" then restart

### Azure OpenAI Issues:
**Problem**: Semantic Kernel initialization fails
**Solution**: Verify environment variables in `.env` file
```bash
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4
```

### Function App Startup Issues:
**Problem**: Functions won't start
**Solution**: 
1. Check Python environment: `python --version`
2. Install dependencies: `pip install -r requirements.txt`
3. Verify Azure Functions Core Tools: `func --version`

### STAC API Issues:
**Problem**: No satellite data returned
**Solution**:
1. Check Microsoft Planetary Computer API status
2. Verify bounding box calculations
3. Check collection names and parameters

### React UI Issues:
**Problem**: UI won't load or API calls fail
**Solution**:
1. Check if backend services are running
2. Verify ports 7071 and 7072 are accessible
3. Check browser console for JavaScript errors

## 📊 Debugging Checklist

### Before Starting:
- [ ] Environment variables configured (`.env` file)
- [ ] All dependencies installed (`npm install`, `pip install -r requirements.txt`)
- [ ] Azure Functions Core Tools installed
- [ ] No port conflicts (kill existing processes)

### During Debugging:
- [ ] All three services running on correct ports
- [ ] Health endpoints responding (7071/api/health, 7072/api/health)
- [ ] Browser DevTools open for network monitoring
- [ ] Appropriate breakpoints set
- [ ] Log levels set to Debug for detailed output

### Testing Flow:
- [ ] React UI loads at http://localhost:5173
- [ ] Can enter natural language query
- [ ] Query reaches Router Function (check logs)
- [ ] Semantic translation works (check breakpoints)
- [ ] STAC function receives call (check logs)
- [ ] Satellite data returns successfully
- [ ] Map renders results correctly

## 🎯 Performance Monitoring

### Response Time Targets:
- **Router Function**: < 5 seconds (including AI processing)
- **STAC Function**: < 10 seconds (including Microsoft PC API)
- **Total End-to-End**: < 15 seconds

### Memory Usage:
- Monitor function app memory in VSCode integrated terminal
- Watch for memory leaks during repeated requests

### API Rate Limits:
- Azure OpenAI: Monitor token usage and rate limits
- Microsoft Planetary Computer: Respect API rate limits

## 📝 Debugging Best Practices

1. **Start Simple**: Test with basic queries first
2. **Isolate Components**: Debug individual functions before testing integration
3. **Use Health Endpoints**: Always verify services are responsive
4. **Monitor Logs**: Keep terminal output visible during debugging
5. **Save Configurations**: Use VSCode debugging configurations for consistency
6. **Document Issues**: Record problems and solutions for team reference

## 🔧 Advanced Debugging

### Remote Debugging:
For deployed Azure Functions, use Application Insights for remote debugging and monitoring.

### Performance Profiling:
Use Python profiling tools to identify bottlenecks in semantic translation and STAC processing.

### Load Testing:
Test with multiple concurrent requests to verify system stability under load.

---

**Happy Debugging! 🐛→✨**

For additional support, check the `documentation/` folder for architecture details and known issues.
