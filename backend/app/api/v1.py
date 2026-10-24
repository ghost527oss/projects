from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import json
import os
import datetime
import traceback
from pathlib import Path
import logging

from app.services.data_ingestion import data_ingestion_service, scheduled_refresh_service, data_source_registry

logger = logging.getLogger("water-management")

router = APIRouter(prefix="/api/v1", tags=["water-management"])

# ============================================================
# Data Models for API Contracts
# ============================================================

class RiskZone(BaseModel):
    name: str
    risk_level: str  # "low", "medium", "high", "very_high"
    flood_depth_estimate: Optional[float] = None  # in meters
    area_sq_km: Optional[float] = None
    geometry: Optional[dict] = None  # GeoJSON geometry
    model_version: Optional[str] = None
    timestamp: Optional[str] = None
    data_source: str = "model"  # "model", "forecast", "observed", "synthetic"

class RainfallScenario(BaseModel):
    name: str
    rainfall_mm: float
    return_period_years: Optional[float] = None
    description: str = ""

class InterventionScenario(BaseModel):
    type: str  # "retention_pond", "drainage_improvement", "green_cover"
    location: dict  # GeoJSON point or cell reference
    parameters: dict  # storage capacity, drainage improvement factor, etc.
    baseline_risk: Optional[RiskZone] = None
    intervention_risk: Optional[RiskZone] = None
    risk_reduction: Optional[float] = None  # percentage

class AlertConfiguration(BaseModel):
    risk_threshold: str  # "medium", "high", "very_high"
    area_id: str
    trigger_condition: str
    notification_channels: List[str] = ["dashboard"]
    severity: str = "medium"

# In-memory storage for demo purposes
risk_zones_db = []
scenarios_db = []
alert_configs_db = []

# ============================================================
# Risk Zones Endpoints
# ============================================================

@router.get("/risk-zones", response_model=List[RiskZone])
async def get_risk_zones():
    """Get all estimated risk zones for the selected area."""
    return risk_zones_db


@router.post("/risk-zones")
async def add_risk_zone(zone: RiskZone):
    """Add a new risk zone calculation."""
    risk_zones_db.append(zone)
    return {"status": "added", "zone_id": len(risk_zones_db) - 1}


# ============================================================
# Scenarios Endpoints
# ============================================================

@router.get("/scenarios", response_model=List[InterventionScenario])
async def get_scenarios():
    """Get all intervention scenarios."""
    return scenarios_db


@router.post("/scenarios")
async def add_scenario(scenario: InterventionScenario):
    """Add a new intervention scenario."""
    scenarios_db.append(scenario)
    return {"status": "added", "scenario_id": len(scenarios_db) - 1}


# ============================================================
# Alerts Endpoints
# ============================================================

@router.get("/alerts/config")
async def get_alert_configs():
    """Get alert configurations."""
    return alert_configs_db


@router.post("/alerts/config")
async def add_alert_config(config: AlertConfiguration):
    """Add a new alert configuration."""
    alert_configs_db.append(config)
    return {"status": "added", "config_id": len(alert_configs_db) - 1}


# ============================================================
# Data Download Endpoints
# ============================================================

class DataDownloadRequest(BaseModel):
    region: Dict[str, Any]  # GeoJSON geometry or bbox [min_lon, min_lat, max_lon, max_lat]
    data_type: str  # "dem", "land_cover", "soil", "rainfall", "osm", "rainfall_forecast", "groundwater"
    source: str  # "open-meteo", "nasapower", "gpm-imerg", "copernicus-dem", "esa-worldcover", "openstreetmap", "isric-soilgrids", "india-wris"
    resolution: Optional[str] = None
    date_range: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


@router.post("/download")
async def trigger_download(req: DataDownloadRequest, background_tasks: BackgroundTasks):
    """Trigger a data download request."""
    try:
        result = await _execute_download(req)
        return {
            "status": "success",
            "region": req.region,
            "data_type": req.data_type,
            "source": req.source,
            "result": result,
            "message": f"Download completed for {req.data_type} from {req.source}"
        }
    except Exception as e:
        logger.error(f"Download failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


async def _execute_download(req: DataDownloadRequest) -> Dict[str, Any]:
    """Execute the actual download based on data type and source."""
    region = req.region
    source = req.source
    params = req.parameters or {}
    
    # Determine bbox from region
    if isinstance(region, list) and len(region) == 4:
        bbox = region  # [min_lon, min_lat, max_lon, max_lat]
    elif isinstance(region, dict) and region.get("type") == "Polygon":
        coords = region["coordinates"][0]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        bbox = [min(lons), min(lats), max(lons), max(lats)]
    elif isinstance(region, dict) and region.get("type") == "Point":
        lon, lat = region["coordinates"]
        bbox = [lon - 0.05, lat - 0.05, lon + 0.05, lat + 0.05]
    else:
        raise ValueError("Invalid region format. Provide bbox [min_lon, min_lat, max_lon, max_lat] or GeoJSON Polygon/Point")
    
    # Extract centroid for point-based APIs
    center_lon = (bbox[0] + bbox[2]) / 2
    center_lat = (bbox[1] + bbox[3]) / 2
    
    if req.data_type == "rainfall_forecast":
        days = params.get("days", 7)
        if source == "open-meteo":
            return await data_ingestion_service.download_open_meteo_forecast(center_lat, center_lon, days)
        elif source == "nasapower":
            end_date = datetime.datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
            return await data_ingestion_service.download_nasa_power(center_lat, center_lon, start_date, end_date)
        else:
            raise ValueError(f"Unsupported source {source} for rainfall_forecast")
    
    elif req.data_type == "rainfall":
        # Historical rainfall
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        if not start_date or not end_date:
            raise ValueError("start_date and end_date required for historical rainfall")
        if source == "open-meteo":
            return await data_ingestion_service.download_open_meteo_archive(center_lat, center_lon, start_date, end_date)
        elif source == "nasapower":
            return await data_ingestion_service.download_nasa_power(center_lat, center_lon, start_date, end_date)
        else:
            raise ValueError(f"Unsupported source {source} for historical rainfall")
    
    elif req.data_type == "osm":
        tags = params.get("tags")
        return await data_ingestion_service.download_osm_data(bbox, tags)
    
    elif req.data_type == "dem":
        resolution = int(req.resolution) if req.resolution else 30
        if source == "copernicus-dem":
            return await data_ingestion_service.download_copernicus_dem(bbox, resolution)
        else:
            raise ValueError(f"Unsupported source {source} for DEM")
    
    elif req.data_type == "land_cover":
        resolution = int(req.resolution) if req.resolution else 10
        year = params.get("year", 2021)
        if source == "esa-worldcover":
            return await data_ingestion_service.download_esa_worldcover(bbox, resolution, year)
        else:
            raise ValueError(f"Unsupported source {source} for land_cover")
    
    elif req.data_type == "soil":
        properties = params.get("properties")
        depth = params.get("depth", "0-5cm")
        if source == "isric-soilgrids":
            return await data_ingestion_service.download_soilgrids(bbox, properties, depth)
        else:
            raise ValueError(f"Unsupported source {source} for soil")
    
    elif req.data_type == "groundwater":
        state = params.get("state")
        district = params.get("district")
        if not state:
            raise ValueError("state required for groundwater data")
        if source == "india-wris":
            return await data_ingestion_service.download_india_wris_groundwater(state, district)
        else:
            raise ValueError(f"Unsupported source {source} for groundwater")
    
    else:
        raise ValueError(f"Unknown data_type: {req.data_type}")


@router.get("/download-status/{job_id}")
async def check_download_status(job_id: str):
    """Check the status of a data download job."""
    # In a real implementation, this would check a job queue
    return {"status": "completed", "job_id": job_id, "message": "Download status check - implement job queue for production"}


# ============================================================
# Data Source Registry Endpoints
# ============================================================

@router.get("/data-sources")
async def list_data_sources():
    """List all available data sources."""
    return {
        "sources": data_source_registry.list_available_sources(),
        "details": {name: data_source_registry.get_source_info(name) for name in data_source_registry.list_available_sources()}
    }


@router.get("/data-sources/{source_name}")
async def get_data_source_info(source_name: str):
    """Get information about a specific data source."""
    info = data_source_registry.get_source_info(source_name)
    if not info:
        raise HTTPException(status_code=404, detail=f"Data source '{source_name}' not found")
    return info


# ============================================================
# Scheduled Refresh Endpoints
# ============================================================

@router.get("/refresh/status")
async def get_refresh_status():
    """Get the status of scheduled refresh service."""
    return scheduled_refresh_service.get_status()


@router.post("/refresh/start")
async def start_refresh(interval_minutes: int = 60):
    """Start the scheduled refresh service."""
    scheduled_refresh_service.refresh_interval = interval_minutes
    scheduled_refresh_service.start()
    return {"status": "started", "interval_minutes": interval_minutes}


@router.post("/refresh/stop")
async def stop_refresh():
    """Stop the scheduled refresh service."""
    scheduled_refresh_service.stop()
    return {"status": "stopped"}


@router.post("/refresh/trigger")
async def trigger_refresh(region: Dict[str, Any], source: str = "open-meteo"):
    """Manually trigger a forecast refresh for a region."""
    result = await scheduled_refresh_service.refresh_forecast_for_region(region, source)
    return result


# ============================================================
# Cached Data Endpoints
# ============================================================

@router.get("/cached-data")
async def list_cached_data(category: str = "raw"):
    """List all cached data files."""
    base_dir = Path(data_ingestion_service._get_dir(category))
    if not base_dir.exists():
        return {"files": []}
    
    files = []
    for f in base_dir.glob("*"):
        if f.is_file():
            files.append({
                "name": f.name,
                "size_bytes": f.stat().st_size,
                "modified": datetime.datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
    return {"files": files, "category": category}


@router.get("/cached-data/{category}/{name}")
async def get_cached_data(category: str, name: str):
    """Get a cached data file."""
    # Remove extension if provided
    if name.endswith(".geojson") or name.endswith(".json"):
        name = name.rsplit(".", 1)[0]
    
    data = data_ingestion_service.load_cached_geojson(name, category)
    if data is None:
        # Try raster
        info = data_ingestion_service.load_cached_raster_info(name, category)
        if info.get("exists"):
            return {"type": "raster", "info": info}
        raise HTTPException(status_code=404, detail=f"Cached data '{name}' not found in {category}")
    
    return {"type": "geojson", "data": data}


# ============================================================
# Coordinate Reference System Endpoint
# ============================================================

class CRSRequest(BaseModel):
    wkt: str


@router.post("/crs/convert")
async def convert_crs(req: CRSRequest):
    """Convert coordinates between reference systems."""
    return {
        "status": "coordinate_conversion_placeholder",
        "input_wkt": req.wkt,
        "message": "CRS conversion endpoint - implementation pending"
    }