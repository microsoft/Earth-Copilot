# 🐛 Earth Copilot Debugging Setup

This setup provides comprehensive debugging capabilities for all Earth Copilot components, allowing you to trace requests end-to-end from the React UI through the Router Function App and STAC Function App.

## 🚀 Quick Start

### 1. **One-Click Debug Start**
Use VSCode Command Palette (`Ctrl+Shift+P`) → "Tasks: Run Task" → "🚀 Debug Full Earth Copilot System"

### 2. **Manual Debug Start**
1. Open VSCode in this workspace
2. Go to Run and Debug (`Ctrl+Shift+D`)
3. Select "🚀 Debug Full Earth Copilot System"
4. Press `F5` to start debugging

### 3. **Script-Based Start**
```powershell
# Basic startup
./debug-startup.ps1

# Clean start (kills existing processes)
./debug-startup.ps1 -Clean

# Debug mode with enhanced logging
./debug-startup.ps1 -Debug

# Skip React UI startup
./debug-startup.ps1 -SkipUI
```

## 🧪 Testing Your Setup

### Quick Health Check
```powershell
./debug-test.ps1 -TestType health
```

### End-to-End Query Test
```powershell
./debug-test.ps1 -TestType query -Query "Show me wildfire damage in California from August 2024"
```

### Comprehensive Test Suite
```powershell
./debug-test.ps1 -TestType all -Verbose
```

## 🎯 Component-Specific Debugging

### React UI (Port 5173)
- **Debug Configuration**: "⚛️ Debug React UI (Chrome/Edge)"
- **Browser DevTools**: F12 → Console/Network tabs
- **Proxy Monitoring**: Vite config includes proxy logging
- **Key Breakpoints**: API service calls, map rendering, chat interactions

### Router Function App (Port 7071)
- **Debug Configuration**: "🌍 Debug Router Function App (Port 7071)"
- **Key Breakpoints**:
  - `function_app.py:1120` - Query endpoint entry
  - `semantic_translator.py:902` - Main translation method
  - `semantic_translator.py:210` - Entity extraction
  - `semantic_translator.py:580` - Location resolution

### STAC Function App (Port 7072)
- **Debug Configuration**: "🔍 Debug STAC Function App (Port 7072)"
- **Key Breakpoints**:
  - `function_app.py:51` - STAC search entry
  - `function_app.py:130` - Query building
  - `function_app.py:74` - Microsoft PC API calls

## 🔍 Debugging Features

### Enhanced Logging
- **Debug Level**: All functions configured for detailed logging
- **Request Tracing**: HTTP requests logged with full details
- **Error Context**: Enhanced error messages with suggestions
- **Performance Metrics**: Response times and data volumes

### Breakpoint Strategies
1. **Entry Points**: Set breakpoints at main function entries
2. **Data Flow**: Monitor data transformation between functions
3. **Error Paths**: Debug exception handling and fallbacks
4. **External APIs**: Monitor Azure OpenAI and Microsoft PC calls

### Network Monitoring
- **React → Router**: Browser DevTools Network tab
- **Router → STAC**: Function app logs
- **STAC → Microsoft PC**: Enhanced logging in STAC function

## 🛠 Debugging Scenarios

### Scenario 1: Semantic Kernel Issues
**Problem**: Natural language processing fails
**Debug Path**:
1. Set breakpoint in `semantic_translator.py:902` (`translate_query`)
2. Check Azure OpenAI environment variables
3. Monitor entity extraction in `extract_entities` method
4. Verify location resolution with Nominatim API

### Scenario 2: No Satellite Data Returned
**Problem**: STAC search returns empty results
**Debug Path**:
1. Set breakpoint in `stac_search_function/function_app.py:51`
2. Verify collection selection logic
3. Check bounding box coordinates
4. Monitor Microsoft Planetary Computer API response

### Scenario 3: Map Not Rendering
**Problem**: React UI shows no map data
**Debug Path**:
1. Check browser console for JavaScript errors
2. Monitor Network tab for failed API calls
3. Set breakpoints in `MapView.tsx` component
4. Verify STAC data format and structure

### Scenario 4: Location Resolution Issues
**Problem**: Wrong coordinates for location queries
**Debug Path**:
1. Set breakpoint in `semantic_translator.py:590` (`resolve_location_to_bbox`)
2. Check Nominatim API responses
3. Verify bounding box validation
4. Test with known location names

## 📊 Performance Debugging

### Response Time Monitoring
- **Router Function**: < 5 seconds (including AI processing)
- **STAC Function**: < 10 seconds (including Microsoft PC API)
- **Total End-to-End**: < 15 seconds

### Memory Usage
Monitor function app memory in VSCode integrated terminal during debugging.

### API Rate Limits
- **Azure OpenAI**: Monitor token usage and rate limits
- **Microsoft Planetary Computer**: Respect API rate limits

## 🔧 Advanced Debugging

### Remote Debugging
Use "🌐 Attach to Router/STAC Function" configurations for remote debugging scenarios.

### Hot Reload
- **React UI**: Vite provides instant hot reload
- **Function Apps**: Use file watching for automatic restarts

### Source Maps
- **React**: TypeScript source maps enabled for debugging
- **Python**: Enhanced stack traces with source context

## 📋 Debugging Checklist

### Before Starting
- [ ] Environment variables set (`.env` file)
- [ ] All dependencies installed
- [ ] No port conflicts
- [ ] Azure Functions Core Tools installed

### During Debugging
- [ ] All services running on correct ports
- [ ] Breakpoints set at key locations
- [ ] Browser DevTools open
- [ ] Log levels set to Debug

### Common Issues
- **Port conflicts**: Use `debug-startup.ps1 -Clean`
- **Azure OpenAI errors**: Check environment variables
- **Function startup issues**: Verify Python environment
- **STAC API issues**: Check Microsoft PC API status

## 🎮 VSCode Extensions Recommended

For optimal debugging experience, install these VSCode extensions:
- **Python** - Python language support
- **Azure Functions** - Azure Functions development
- **Debugger for Chrome** - React debugging in Chrome
- **REST Client** - API testing
- **Thunder Client** - API testing alternative

## 📚 Additional Resources

- [Azure Functions Python Debugging](https://docs.microsoft.com/en-us/azure/azure-functions/functions-reference-python)
- [React DevTools](https://reactjs.org/blog/2019/08/15/new-react-devtools.html)
- [Chrome DevTools](https://developers.google.com/web/tools/chrome-devtools)

---

**Happy Debugging! 🐛→✨**

For questions or issues, check the main `DEBUG_GUIDE.md` or create an issue in the repository.
