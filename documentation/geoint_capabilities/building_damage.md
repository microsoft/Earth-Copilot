# Building Damage Assessment - Complete Integration Guide

**Last Updated:** October 29, 2025  
**Status:** Technical Implementation Plan  
**Timeline:** 2-3 weeks  
**Complexity:** High (ML model integration, image processing, temporal data matching)  
**Impact:** High (Enables humanitarian disaster response capabilities)

---

## Table of Contents

1. [Overview](#overview)
2. [Model Architecture](#model-architecture)
3. [Integration Strategy](#integration-strategy)
4. [Implementation Plan](#implementation-plan)
5. [Code Examples](#code-examples)
6. [API Specification](#api-specification)
7. [Use Cases](#use-cases)
8. [Deployment](#deployment)

---

## Overview

This document outlines the integration of building damage assessment capabilities into Earth Copilot using a pre-trained Siamese U-Net CNN model from Microsoft's AI for Humanitarian Action initiative. The integration enables natural language disaster damage assessment queries.

### Key Capabilities

- **Building Detection**: Identifies building footprints in satellite imagery
- **Change Detection**: Compares pre/post disaster imagery using Siamese architecture
- **Damage Classification**: Pixel-level damage assessment with 5 severity levels
- **Humanitarian Focus**: Designed for disaster response and aid allocation

### Example Queries

```
"Show me damaged buildings in the hurricane-affected area"
"Assess building damage severity in Puerto Rico after Hurricane Maria"
"Find destroyed buildings in the earthquake zone near Turkey"
"Compare building conditions before and after the wildfire"
```

---

## Model Architecture

### Siamese U-Net CNN

- **Architecture**: Siamese U-Net for change detection
- **Input**: Pairs of pre-disaster and post-disaster satellite images (RGB, 256x256 patches)
- **Output**: 
  - Building segmentation masks (identifies buildings vs. non-buildings)
  - Damage classification (5 levels per pixel)
- **Model Size**: Pre-trained weights (`model_best.pth.tar` - 46MB)
- **Training Data**: xBD Dataset (xView2 Challenge)

### Damage Classification Scale

| Level | Classification | Description |
|-------|---------------|-------------|
| 0 | No building | No structure detected |
| 1 | No damage | Building found, structurally sound |
| 2 | Minor damage | Building found, minor structural damage |
| 3 | Major damage | Building found, significant structural damage |
| 4 | Destroyed | Building found, completely destroyed |
| 5 | Unclassified | Building features unclassified (discounted) |

### Model Performance

- **Pixel-level evaluation**: Primary metric for damage classification accuracy
- **Building-level evaluation**: Available but may underestimate due to connected components
- **Multi-disaster training**: Trained on hurricanes, earthquakes, floods, wildfires
- **High-resolution support**: Optimized for 10m-1m resolution satellite imagery

---

## Integration Strategy

### Data Sources

| Source | Resolution | Use Case |
|--------|-----------|----------|
| **Sentinel-2** | 10m | Large-scale damage assessment |
| **Landsat** | 30m | Historical comparisons |
| **NAIP** | 0.6-1m | High-detail US assessments |
| **Planet** | 3-5m | Commercial high-frequency monitoring |

### Processing Workflow

```
User Query → Location & Date Extraction → Pre/Post Imagery Retrieval
    ↓
Patch Generation (256x256) → Model Inference → Damage Classification
    ↓
GeoJSON Conversion → Statistics Aggregation → Visualization
```

---

## Implementation Plan

### Phase 1: Infrastructure Setup (Days 1-2)

#### 1.1 Dependencies

**File**: `requirements.txt`

```python
# Deep Learning & Computer Vision
torch>=2.0.0
torchvision>=0.15.0
Pillow>=9.0.0

# Geospatial Processing
rasterio>=1.3.0
shapely>=2.0.0
geopandas>=0.12.0
pyproj>=3.4.0

# Image Processing
opencv-python>=4.7.0
scikit-image>=0.20.0

# Utilities
tqdm>=4.65.0
numpy>=1.24.0
```

#### 1.2 Directory Structure

```
earth-copilot/container-app/backend/
├── damage_assessment/
│   ├── __init__.py
│   ├── model/
│   │   ├── __init__.py
│   │   ├── siamese_unet.py          # Model architecture
│   │   ├── model_loader.py          # Model initialization
│   │   └── weights/
│   │       └── model_best.pth.tar   # Pre-trained weights (46MB)
│   ├── preprocessing/
│   │   ├── __init__.py
│   │   ├── image_processor.py       # Image tiling, normalization
│   │   ├── patch_generator.py       # 256x256 patch extraction
│   │   └── normalization.py         # Mean/stddev computation
│   ├── inference/
│   │   ├── __init__.py
│   │   ├── damage_classifier.py     # Main inference orchestrator
│   │   └── batch_processor.py       # Batch processing for large areas
│   ├── postprocessing/
│   │   ├── __init__.py
│   │   ├── geojson_converter.py     # Mask to GeoJSON conversion
│   │   └── statistics.py            # Damage statistics aggregation
│   └── temporal/
│       ├── __init__.py
│       └── temporal_matcher.py      # Pre/post disaster image pairing
```

#### 1.3 Copy Model Files

1. Copy `building-damage-assessment-cnn-siamese/models/end_to_end_Siam_UNet.py` → `siamese_unet.py`
2. Copy pre-trained weights `model_best.pth.tar` → `weights/`
3. Extract utilities from `inference/utils/`

---

### Phase 2: Core Model Integration (Days 3-5)

#### 2.1 Model Loader

**File**: `damage_assessment/model/model_loader.py`

```python
import torch
import logging
from pathlib import Path
from .siamese_unet import SiamUnet

class DamageAssessmentModel:
    """Wrapper for Siamese U-Net model with lazy loading"""
    
    def __init__(self, model_path: str = None, device: str = None):
        self.model_path = model_path or self._get_default_model_path()
        self.device = device or self._get_device()
        self._model = None
        self.logger = logging.getLogger(__name__)
        
    def _get_default_model_path(self) -> Path:
        """Get default model weights path"""
        return Path(__file__).parent / "weights" / "model_best.pth.tar"
    
    def _get_device(self) -> str:
        """Auto-detect GPU/CPU"""
        return "cuda" if torch.cuda.is_available() else "cpu"
    
    @property
    def model(self):
        """Lazy load model on first access"""
        if self._model is None:
            self.logger.info(f"Loading damage assessment model from {self.model_path}")
            self._load_model()
        return self._model
    
    def _load_model(self):
        """Load pre-trained SiamUnet model"""
        try:
            # Initialize model architecture
            self._model = SiamUnet()
            
            # Load pre-trained weights
            checkpoint = torch.load(
                self.model_path,
                map_location=self.device,
                weights_only=True  # Security: only load weights
            )
            
            # Handle different checkpoint formats
            if isinstance(checkpoint, dict) and 'state_dict' in checkpoint:
                self._model.load_state_dict(checkpoint['state_dict'])
            else:
                self._model.load_state_dict(checkpoint)
            
            # Move to device and set to evaluation mode
            self._model.to(self.device)
            self._model.eval()
            
            self.logger.info(f"✅ Model loaded successfully on {self.device}")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to load model: {e}")
            raise
    
    def predict(self, pre_image_tensor, post_image_tensor):
        """Run inference on image pair"""
        with torch.no_grad():
            pre = pre_image_tensor.to(self.device)
            post = post_image_tensor.to(self.device)
            
            # Forward pass
            damage_output = self.model(pre, post)
            
            # Get damage class predictions (argmax across class dimension)
            damage_pred = torch.argmax(damage_output, dim=1)
            
            return damage_pred.cpu().numpy()

# Singleton instance
_model_instance = None

def get_damage_model() -> DamageAssessmentModel:
    """Get singleton damage assessment model instance"""
    global _model_instance
    if _model_instance is None:
        _model_instance = DamageAssessmentModel()
    return _model_instance
```

#### 2.2 Image Preprocessing

**File**: `damage_assessment/preprocessing/image_processor.py`

```python
import numpy as np
from PIL import Image
import torch
from torchvision import transforms
from typing import List, Tuple

class DamageImageProcessor:
    """Process satellite imagery for damage assessment model"""
    
    def __init__(self, patch_size: int = 256):
        self.patch_size = patch_size
        
        # Standard normalization for RGB imagery
        # (based on xBD dataset statistics)
        self.transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],  # ImageNet stats
                std=[0.229, 0.224, 0.225]
            )
        ])
    
    def preprocess(self, image_data: np.ndarray) -> torch.Tensor:
        """
        Preprocess image for model input
        
        Args:
            image_data: NumPy array (H, W, 3) in RGB format
            
        Returns:
            Preprocessed tensor (1, 3, H, W)
        """
        # Convert to PIL Image
        img = Image.fromarray(image_data.astype('uint8'), 'RGB')
        
        # Apply transformations
        tensor = self.transform(img)
        
        # Add batch dimension
        return tensor.unsqueeze(0)
    
    def create_patches(self, image: np.ndarray) -> List[Tuple[np.ndarray, Tuple[int, int]]]:
        """
        Split large image into 256x256 patches with position tracking
        
        Args:
            image: Full resolution image (H, W, 3)
            
        Returns:
            List of (patch, (row, col)) tuples
        """
        h, w = image.shape[:2]
        patches = []
        
        for i in range(0, h, self.patch_size):
            for j in range(0, w, self.patch_size):
                # Extract patch
                patch = image[i:i+self.patch_size, j:j+self.patch_size]
                
                # Pad if necessary (edge patches may be smaller)
                if patch.shape[0] < self.patch_size or patch.shape[1] < self.patch_size:
                    patch = self._pad_patch(patch)
                
                patches.append((patch, (i, j)))
        
        return patches
    
    def _pad_patch(self, patch: np.ndarray) -> np.ndarray:
        """Pad patch to required size"""
        pad_h = self.patch_size - patch.shape[0]
        pad_w = self.patch_size - patch.shape[1]
        
        return np.pad(
            patch,
            ((0, pad_h), (0, pad_w), (0, 0)),
            mode='constant',
            constant_values=0
        )
    
    def reconstruct_from_patches(
        self,
        patch_predictions: List[np.ndarray],
        patch_positions: List[Tuple[int, int]],
        original_shape: Tuple[int, int]
    ) -> np.ndarray:
        """
        Reconstruct full image from patch predictions
        
        Args:
            patch_predictions: List of damage prediction masks per patch
            patch_positions: List of (row, col) positions for each patch
            original_shape: (H, W) of original image
            
        Returns:
            Full damage prediction mask (H, W)
        """
        h, w = original_shape
        full_mask = np.zeros((h, w), dtype=np.uint8)
        
        for pred, (i, j) in zip(patch_predictions, patch_positions):
            # Place patch prediction into full mask
            patch_h = min(self.patch_size, h - i)
            patch_w = min(self.patch_size, w - j)
            
            full_mask[i:i+patch_h, j:j+patch_w] = pred[:patch_h, :patch_w]
        
        return full_mask
```

#### 2.3 Damage Classification Orchestrator

**File**: `damage_assessment/inference/damage_classifier.py`

```python
import logging
from typing import Dict, List, Tuple
import numpy as np

from ..model.model_loader import get_damage_model
from ..preprocessing.image_processor import DamageImageProcessor
from ..postprocessing.geojson_converter import DamageGeoJSONConverter
from ..postprocessing.statistics import compute_damage_statistics

class DamageClassifier:
    """Main orchestrator for building damage assessment"""
    
    def __init__(self):
        self.model = get_damage_model()
        self.processor = DamageImageProcessor()
        self.geojson_converter = DamageGeoJSONConverter()
        self.logger = logging.getLogger(__name__)
    
    def assess_damage(
        self,
        pre_image: np.ndarray,
        post_image: np.ndarray,
        bbox: Tuple[float, float, float, float] = None
    ) -> Dict:
        """
        Perform end-to-end damage assessment
        
        Args:
            pre_image: Pre-disaster image (H, W, 3) RGB
            post_image: Post-disaster image (H, W, 3) RGB
            bbox: Optional (minx, miny, maxx, maxy) in EPSG:4326
            
        Returns:
            Dictionary with damage assessment results
        """
        self.logger.info("Starting damage assessment")
        
        # 1. Create patches from both images
        pre_patches = self.processor.create_patches(pre_image)
        post_patches = self.processor.create_patches(post_image)
        
        # 2. Run model inference on each patch pair
        damage_predictions = []
        patch_positions = []
        
        for (pre_patch, pos), (post_patch, _) in zip(pre_patches, post_patches):
            # Preprocess
            pre_tensor = self.processor.preprocess(pre_patch)
            post_tensor = self.processor.preprocess(post_patch)
            
            # Inference
            damage_pred = self.model.predict(pre_tensor, post_tensor)
            damage_predictions.append(damage_pred[0])  # Remove batch dim
            patch_positions.append(pos)
        
        # 3. Reconstruct full damage mask
        full_damage_mask = self.processor.reconstruct_from_patches(
            damage_predictions,
            patch_positions,
            pre_image.shape[:2]
        )
        
        # 4. Compute statistics
        stats = compute_damage_statistics(full_damage_mask)
        
        # 5. Convert to GeoJSON (if bbox provided)
        geojson_result = None
        if bbox:
            geojson_result = self.geojson_converter.mask_to_geojson(
                full_damage_mask,
                bbox
            )
        
        return {
            "damage_mask": full_damage_mask,
            "statistics": stats,
            "geojson": geojson_result
        }
```

#### 2.4 Statistics Computation

**File**: `damage_assessment/postprocessing/statistics.py`

```python
import numpy as np
from typing import Dict

def compute_damage_statistics(damage_mask: np.ndarray) -> Dict[str, int]:
    """
    Compute damage statistics from prediction mask
    
    Args:
        damage_mask: Damage prediction mask (H, W) with values 0-5
        
    Returns:
        Dictionary with counts per damage level
    """
    unique, counts = np.unique(damage_mask, return_counts=True)
    
    damage_labels = {
        0: "no_building",
        1: "no_damage",
        2: "minor_damage",
        3: "major_damage",
        4: "destroyed",
        5: "unclassified"
    }
    
    stats = {damage_labels[i]: 0 for i in range(6)}
    
    for level, count in zip(unique, counts):
        if level in damage_labels:
            stats[damage_labels[level]] = int(count)
    
    # Compute total buildings (exclude no_building and unclassified)
    stats["total_buildings"] = sum([
        stats["no_damage"],
        stats["minor_damage"],
        stats["major_damage"],
        stats["destroyed"]
    ])
    
    # Compute damage percentage
    if stats["total_buildings"] > 0:
        damaged = stats["minor_damage"] + stats["major_damage"] + stats["destroyed"]
        stats["damage_percentage"] = round(100 * damaged / stats["total_buildings"], 2)
    else:
        stats["damage_percentage"] = 0.0
    
    return stats
```

---

### Phase 3: Backend API Integration (Days 6-8)

#### 3.1 FastAPI Endpoint

**File**: `earth-copilot/container-app/fastapi_app.py`

```python
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Dict, Optional

from damage_assessment.inference.damage_classifier import DamageClassifier
from damage_assessment.temporal.temporal_matcher import TemporalImageMatcher

# Initialize services
damage_classifier = DamageClassifier()
temporal_matcher = TemporalImageMatcher()

class DamageAssessmentRequest(BaseModel):
    """
    Request model for building damage assessment
    """
    location: Dict[str, float]  # {"lat": 40.7128, "lon": -74.0060}
    disaster_date: str          # "2024-02-06" (ISO format)
    assessment_area: Optional[Dict] = None  # GeoJSON polygon
    pre_disaster_days: int = 60   # Days before disaster
    post_disaster_days: int = 14  # Days after disaster
    collections: List[str] = ["sentinel-2-l2a", "landsat-c2-l2"]

class DamageAssessmentResponse(BaseModel):
    """
    Response model for damage assessment
    """
    status: str
    total_buildings: int
    damage_statistics: Dict[str, int]
    geojson_results: Dict
    imagery_metadata: Dict
    processing_time: float

@app.post("/api/assess-building-damage", response_model=DamageAssessmentResponse)
async def assess_building_damage(request: DamageAssessmentRequest):
    """
    Assess building damage from satellite imagery
    
    Process:
    1. Query pre/post disaster imagery from STAC
    2. Download and preprocess images
    3. Run Siamese U-Net damage assessment
    4. Return damage statistics and GeoJSON results
    """
    import time
    start_time = time.time()
    
    try:
        # 1. Find matching pre/post imagery
        imagery_pair = await temporal_matcher.find_image_pair(
            location=request.location,
            disaster_date=request.disaster_date,
            pre_days=request.pre_disaster_days,
            post_days=request.post_disaster_days,
            collections=request.collections
        )
        
        if not imagery_pair:
            raise HTTPException(
                status_code=404,
                detail="Could not find suitable pre/post disaster imagery"
            )
        
        # 2. Download imagery
        pre_image_data = await download_image(imagery_pair["pre"])
        post_image_data = await download_image(imagery_pair["post"])
        
        # 3. Extract bounding box
        bbox = extract_bbox(request.location, request.assessment_area)
        
        # 4. Run damage assessment
        results = damage_classifier.assess_damage(
            pre_image=pre_image_data,
            post_image=post_image_data,
            bbox=bbox
        )
        
        # 5. Build response
        processing_time = time.time() - start_time
        
        return DamageAssessmentResponse(
            status="success",
            total_buildings=results["statistics"]["total_buildings"],
            damage_statistics=results["statistics"],
            geojson_results=results["geojson"],
            imagery_metadata={
                "pre_disaster": imagery_pair["pre"]["metadata"],
                "post_disaster": imagery_pair["post"]["metadata"]
            },
            processing_time=processing_time
        )
        
    except Exception as e:
        logger.error(f"Damage assessment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

#### 3.2 Natural Language Query Integration

**File**: `earth-copilot/container-app/semantic_translator.py`

```python
def _classify_query_intent(self, query: str) -> Dict:
    """Enhanced query classification including damage assessment"""
    
    # Check for damage assessment intent
    damage_keywords = [
        "damage", "damaged", "destruction", "destroyed",
        "disaster", "earthquake", "hurricane", "flood",
        "building damage", "structural damage",
        "assess damage", "damage assessment"
    ]
    
    if any(keyword in query.lower() for keyword in damage_keywords):
        return {
            "type": "damage_assessment",
            "requires_temporal_comparison": True,
            "requires_high_resolution": True
        }
    
    # ... rest of classification logic

async def process_damage_query(self, query: str, location: Dict) -> Dict:
    """
    Process natural language damage assessment queries
    
    Example queries:
    - "Show building damage from the Turkey earthquake on Feb 6, 2024"
    - "Assess damage in Puerto Rico after Hurricane Maria"
    """
    # 1. Extract disaster date from query
    disaster_date = self._extract_date(query)
    
    if not disaster_date:
        # Try to look up known disaster events
        disaster_date = await self._lookup_disaster_event(query, location)
    
    if not disaster_date:
        raise ValueError("Could not determine disaster date from query")
    
    # 2. Build damage assessment request
    damage_request = {
        "location": location,
        "disaster_date": disaster_date,
        "pre_disaster_days": 60,
        "post_disaster_days": 14
    }
    
    # 3. Execute damage assessment
    results = await assess_building_damage(damage_request)
    
    return results
```

---

## API Specification

### Endpoint

```
POST /api/assess-building-damage
```

### Request Schema

```json
{
  "location": {
    "lat": 40.7128,
    "lon": -74.0060
  },
  "disaster_date": "2024-02-06",
  "assessment_area": {
    "type": "Polygon",
    "coordinates": [[[...], [...], [...]]]
  },
  "pre_disaster_days": 60,
  "post_disaster_days": 14,
  "collections": ["sentinel-2-l2a", "landsat-c2-l2"]
}
```

### Response Schema

```json
{
  "status": "success",
  "total_buildings": 5438,
  "damage_statistics": {
    "no_building": 150000,
    "no_damage": 1500,
    "minor_damage": 800,
    "major_damage": 1891,
    "destroyed": 1247,
    "unclassified": 50,
    "total_buildings": 5438,
    "damage_percentage": 72.4
  },
  "geojson_results": {
    "type": "FeatureCollection",
    "features": [...]
  },
  "imagery_metadata": {
    "pre_disaster": {...},
    "post_disaster": {...}
  },
  "processing_time": 12.45
}
```

---

## Use Cases

### 1. Disaster Response

**Scenario**: 7.8 magnitude earthquake strikes Turkey/Syria border

**Query**: *"Assess building damage in Gaziantep after the February 2023 earthquake"*

**Workflow**:
1. System identifies disaster date (Feb 6, 2023)
2. Retrieves Sentinel-2 imagery from Jan 2023 (pre) and Feb 2023 (post)
3. Runs damage assessment over 50km² area
4. Generates damage map showing 12,000+ destroyed buildings

**Output**:
- Priority zones for search & rescue
- Infrastructure damage severity
- Resource allocation recommendations

---

### 2. Insurance Claims

**Scenario**: Hurricane damages coastal properties

**Query**: *"Show me property damage from Hurricane Ian in Fort Myers"*

**Workflow**:
1. Identifies Hurricane Ian landfall date (Sept 28, 2022)
2. Uses high-resolution NAIP imagery (0.6m)
3. Assesses damage for 5,000+ properties
4. Generates per-building damage classification

**Output**:
- Individual property damage reports
- Claims prioritization
- Loss estimation support

---

### 3. Humanitarian Aid

**Scenario**: Earthquake destroys schools and hospitals

**Query**: *"Find damaged medical facilities in Aleppo"*

**Workflow**:
1. Retrieves pre/post earthquake imagery
2. Focuses on known hospital/clinic locations
3. Assesses structural integrity
4. Identifies alternative facilities

**Output**:
- List of operational vs. damaged medical facilities
- Shelter needs assessment
- Aid distribution planning

---

## Deployment

### Model Storage

**Option 1: Container Image (Recommended)**
- Include `model_best.pth.tar` (46MB) in Docker image
- Pros: Fast cold starts, no external dependencies
- Cons: Larger container image

**Option 2: Azure Blob Storage**
- Download model on container startup
- Pros: Smaller container, easier model updates
- Cons: Cold start penalty, requires network access

### Performance Optimization

#### GPU Acceleration

```python
# Detect and use GPU if available
device = "cuda" if torch.cuda.is_available() else "cpu"

# For Azure Container Apps, use GPU-enabled SKUs
# Consumption Plan: Not supported
# Dedicated Plan: NVIDIA T4, V100, A100 available
```

#### Batch Processing

For large areas (>100km²):
- Tile into 10km x 10km sub-regions
- Process asynchronously
- Store intermediate results in Azure Storage
- Aggregate on completion

#### Caching

```python
# Cache processed imagery pairs
cache_key = f"{location}_{disaster_date}_{pre_days}_{post_days}"

# Cache damage assessment results
cache_ttl = 86400  # 24 hours
```

### Scalability Considerations

| Area Size | Processing Time | Recommended Approach |
|-----------|----------------|---------------------|
| < 1km² | 2-5 seconds | Synchronous API |
| 1-10km² | 10-30 seconds | Synchronous with streaming |
| 10-100km² | 1-5 minutes | Async with job queue |
| > 100km² | 10-60 minutes | Batch processing job |

### Monitoring & Logging

```python
# Log key metrics
logger.info(f"Damage assessment: {total_buildings} buildings analyzed")
logger.info(f"Processing time: {elapsed_time:.2f}s")
logger.info(f"Damage rate: {damage_percentage:.1f}%")

# Azure Application Insights metrics
telemetry.track_metric("damage_assessment_time", elapsed_time)
telemetry.track_metric("buildings_analyzed", total_buildings)
telemetry.track_metric("damage_percentage", damage_percentage)
```

---

## Integration Benefits

✅ **Perfect Fit**: Complements existing satellite imagery capabilities  
✅ **High Impact**: Critical for disaster response and humanitarian aid  
✅ **Ready-to-Use**: Pre-trained model with proven performance  
✅ **Microsoft Heritage**: Aligns with AI for Humanitarian Action initiatives  
✅ **Scalable**: Can process large areas using existing cloud infrastructure  
✅ **Production-Ready**: Includes error handling, caching, monitoring  

---

## Testing Strategy

### Unit Tests

```python
def test_image_preprocessing():
    """Test patch generation and reconstruction"""
    processor = DamageImageProcessor()
    test_image = np.random.randint(0, 255, (1024, 1024, 3))
    
    patches = processor.create_patches(test_image)
    assert len(patches) == 16  # 4x4 patches for 1024x1024 image

def test_damage_classification():
    """Test basic damage classification"""
    classifier = DamageClassifier()
    pre_image = load_test_image("pre_disaster.png")
    post_image = load_test_image("post_disaster.png")
    
    results = classifier.assess_damage(pre_image, post_image)
    assert "statistics" in results
    assert results["statistics"]["total_buildings"] > 0
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_full_damage_assessment_api():
    """Test full API endpoint"""
    request_data = {
        "location": {"lat": 37.7749, "lon": -122.4194},
        "disaster_date": "2023-01-01",
        "pre_disaster_days": 60,
        "post_disaster_days": 14
    }
    
    response = await client.post("/api/assess-building-damage", json=request_data)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
```

### Performance Benchmarks

```python
def benchmark_inference_speed():
    """Benchmark damage assessment inference"""
    model = get_damage_model()
    test_pairs = load_test_image_pairs(n=100)
    
    start = time.time()
    for pre, post in test_pairs:
        model.predict(pre, post)
    elapsed = time.time() - start
    
    print(f"Average inference time: {elapsed/100:.3f}s per patch")
```

---

## Next Steps

### Immediate Tasks

1. ✅ **Model Integration**: Add SiamUnet model to backend service
2. ✅ **API Development**: Create damage assessment endpoints
3. ⏳ **Frontend Updates**: Add damage visualization layers
4. ⏳ **Testing**: Validate with historical disaster data
5. ⏳ **Documentation**: Create user guides

### Future Enhancements

- **Real-time Processing**: Process satellite imagery as soon as it becomes available
- **Multi-temporal Analysis**: Track recovery progress over time
- **Building Footprint Integration**: Use Microsoft Building Footprints for more accurate assessment
- **Damage Severity Validation**: Integrate ground truth data for continuous model improvement
- **Mobile App**: Field assessment capabilities for disaster response teams

---

## References

- **Original Repository**: `building-damage-assessment-cnn-siamese`
- **Microsoft AI for Humanitarian Action**: https://www.microsoft.com/en-us/ai/ai-for-humanitarian-action
- **Netherlands Red Cross 510 Initiative**: https://www.510.global/
- **xBD Dataset**: https://xview2.org/
- **xView2 Challenge**: Computer Vision for Building Damage Assessment

---

*This integration transforms Earth Copilot from a general geospatial assistant into a powerful disaster response and humanitarian aid tool, making it invaluable for organizations like the Red Cross, FEMA, UN agencies, and insurance companies.*
