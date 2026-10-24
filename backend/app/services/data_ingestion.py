import os
import json
import datetime
import logging
import asyncio
from typing import Optional, Dict, Any, List
from pathlib import Path

import httpx
import aiofiles

logger = logging.getLogger("water-management")


class DataIngestionService:
    """Service for ingesting and caching geospatial data."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.raw_dir = os.path.join(data_dir, "raw")
        self.processed_dir = os.path.join(data_dir, "processed")
        self.sample_dir = os.path.join(data_dir, "sample")

    def cache_geojson(self, name: str, geojson_data: dict, category: str = "raw") -> str:
        """Cache a GeoJSON object to the appropriate directory."""
        target_dir = self._get_dir(category)
        filepath = os.path.join(target_dir, f"{name}.geojson")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, "w") as f:
            json.dump(geojson_data, f, indent=2)

        logger.info(f"Cached GeoJSON to {filepath}")
        return filepath

    def cache_raster(self, name: str, raster_path: str, category: str = "raw") -> str:
        """Cache a raster file to the appropriate directory."""
        target_dir = self._get_dir(category)
        destination = os.path.join(target_dir, f"{name}.tif")
        os.makedirs(os.path.dirname(destination), exist_ok=True)

        import shutil
        shutil.copy2(raster_path, destination)

        logger.info(f"Cached raster to {destination}")
        return destination

    def _get_dir(self, category: str) -> str:
        """Get the target directory for a data category."""
        categories = {
            "raw": self.raw_dir,
            "processed": self.processed_dir,
            "sample": self.sample_dir,
        }
        return categories.get(category, self.raw_dir)

    def load_cached_geojson(self, name: str, category: str = "raw") -> Optional[dict]:
        """Load a cached GeoJSON object."""
        filepath = os.path.join(self._get_dir(category), f"{name}.geojson")
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                return json.load(f)
        return None

    def load_cached_raster_info(self, name: str, category: str = "raw") -> Optional[dict]:
        """Get info about a cached raster file."""
        filepath = os.path.join(self._get_dir(category), f"{name}.tif")
        if os.path.exists(filepath):
            return {
                "path": filepath,
                "exists": True,
                "size_bytes": os.path.getsize(filepath),
            }
        return {"exists": False}

    # ============================================================
    # Data Download Methods
    # ============================================================

    async def download_open_meteo_forecast(
        self,
        latitude: float,
        longitude: float,
        days: int = 7,
        hourly_params: Optional[List[str]] = None,
        daily_params: Optional[List[str]] = None,
    ) -> dict:
        """Download forecast data from Open-Meteo API."""
        if hourly_params is None:
            hourly_params = ["temperature_2m", "precipitation", "weathercode", "relative_humidity_2m"]
        if daily_params is None:
            daily_params = ["temperature_2m_max", "temperature_2m_min", "precipitation_sum", "weathercode"]

        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(hourly_params),
            "daily": ",".join(daily_params),
            "forecast_days": days,
            "timezone": "auto",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        # Cache the response
        cache_name = f"openmeteo_forecast_{latitude}_{longitude}_{datetime.datetime.now().strftime('%Y%m%d')}"
        self.cache_geojson(cache_name, data)

        return data

    async def download_open_meteo_archive(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
        hourly_params: Optional[List[str]] = None,
        daily_params: Optional[List[str]] = None,
    ) -> dict:
        """Download historical data from Open-Meteo Archive API (ERA5)."""
        if hourly_params is None:
            hourly_params = ["temperature_2m", "precipitation"]
        if daily_params is None:
            daily_params = ["temperature_2m_max", "temperature_2m_min", "precipitation_sum"]

        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": ",".join(hourly_params),
            "daily": ",".join(daily_params),
            "timezone": "auto",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        cache_name = f"openmeteo_archive_{latitude}_{longitude}_{start_date}_{end_date}"
        self.cache_geojson(cache_name, data)

        return data

    async def download_nasa_power(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
        parameters: Optional[List[str]] = None,
    ) -> dict:
        """Download data from NASA POWER API."""
        if parameters is None:
            parameters = ["PRECTOTCORR", "T2M", "T2M_MAX", "T2M_MIN", "RH2M", "WS2M"]

        url = "https://power.larc.nasa.gov/api/timing/daily"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start": start_date.replace("-", ""),
            "end": end_date.replace("-", ""),
            "parameters": ",".join(parameters),
            "community": "AG",
            "format": "JSON",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        cache_name = f"nasa_power_{latitude}_{longitude}_{start_date}_{end_date}"
        self.cache_geojson(cache_name, data)

        return data

    async def download_osm_data(
        self,
        bbox: List[float],  # [min_lon, min_lat, max_lon, max_lat]
        tags: Optional[Dict[str, str]] = None,
    ) -> dict:
        """Download OSM data using Overpass API."""
        if tags is None:
            tags = {
                "waterway": "river",
                "natural": "water",
                "highway": True,
                "building": True,
            }

        # Build Overpass query
        tag_queries = []
        for k, v in tags.items():
            if v is True:
                tag_queries.append(f'["{k}"]')
            else:
                tag_queries.append(f'["{k}"="{v}"]')

        tag_filter = "".join(tag_queries)
        query = f"""
        [out:json][timeout:60];
        (
          node{tag_filter}({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
          way{tag_filter}({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
          relation{tag_filter}({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
        );
        out geom;
        """

        url = "https://overpass-api.de/api/interpreter"
        headers = {
            "User-Agent": "Climate-Resilient-Water-Management/1.0",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0, headers=headers) as client:
            response = await client.post(url, data={"data": query})
            response.raise_for_status()
            data = response.json()

        # Convert to GeoJSON
        geojson = self._osm_to_geojson(data)

        cache_name = f"osm_{bbox[0]}_{bbox[1]}_{bbox[2]}_{bbox[3]}_{datetime.datetime.now().strftime('%Y%m%d')}"
        self.cache_geojson(cache_name, geojson)

        return geojson

    def _osm_to_geojson(self, osm_data: dict) -> dict:
        """Convert OSM JSON to GeoJSON FeatureCollection."""
        features = []
        for element in osm_data.get("elements", []):
            if element["type"] == "node":
                if "lat" in element and "lon" in element:
                    features.append({
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [element["lon"], element["lat"]]
                        },
                        "properties": element.get("tags", {})
                    })
            elif element["type"] == "way":
                if "geometry" in element:
                    coords = [[node["lon"], node["lat"]] for node in element["geometry"]]
                    # Close polygon if it's an area
                    if element.get("tags", {}).get("area") != "no" and coords[0] != coords[-1]:
                        coords.append(coords[0])
                    geom_type = "Polygon" if coords[0] == coords[-1] else "LineString"
                    features.append({
                        "type": "Feature",
                        "geometry": {
                            "type": geom_type,
                            "coordinates": [coords] if geom_type == "Polygon" else coords
                        },
                        "properties": element.get("tags", {})
                    })

        return {
            "type": "FeatureCollection",
            "features": features
        }

    async def download_copernicus_dem(
        self,
        bbox: List[float],  # [min_lon, min_lat, max_lon, max_lat]
        resolution: int = 30,
    ) -> dict:
        """
        Download Copernicus DEM.
        Note: This is a placeholder - actual Copernicus DEM requires registration
        and specific download process. For now, we'll use SRTM or other alternatives.
        """
        # For actual implementation, would use:
        # - Copernicus DEM download via their API
        # - Or use AWS S3 public datasets
        # - Or use SRTM via NASA Earthdata
        
        # This is a placeholder that returns metadata about what would be downloaded
        result = {
            "status": "placeholder",
            "message": "Copernicus DEM download requires registration. Use SRTM or AWS open data as alternative.",
            "bbox": bbox,
            "resolution": resolution,
            "alternatives": {
                "srtm_aws": f"https://s3.amazonaws.com/elevation-tiles-prod/geotiff/{bbox[0]}/{bbox[1]}.tif",
                "copernicus_glo30": "Requires EEA authentication",
            }
        }
        
        cache_name = f"copernicus_dem_{bbox[0]}_{bbox[1]}_{bbox[2]}_{bbox[3]}"
        self.cache_geojson(cache_name, result)
        
        return result

    async def download_esa_worldcover(
        self,
        bbox: List[float],
        resolution: int = 10,
        year: int = 2021,
    ) -> dict:
        """
        Download ESA WorldCover land cover data.
        Note: This is a placeholder - actual download requires specific API or CLI tool.
        """
        result = {
            "status": "placeholder",
            "message": "ESA WorldCover download requires CLIPDOWN tool or direct download from ESA.",
            "bbox": bbox,
            "resolution": resolution,
            "year": year,
            "download_url": f"https://esa-worldcover.s3.eu-central-1.amazonaws.com/v{year}/{bbox[0]}_{bbox[1]}.tif",
        }
        
        cache_name = f"esa_worldcover_{bbox[0]}_{bbox[1]}_{bbox[2]}_{bbox[3]}_{year}"
        self.cache_geojson(cache_name, result)
        
        return result

    async def download_soilgrids(
        self,
        bbox: List[float],
        properties: Optional[List[str]] = None,
        depth: str = "0-5cm",
    ) -> dict:
        """
        Download ISRIC SoilGrids soil properties.
        """
        if properties is None:
            properties = ["clay", "sand", "silt", "bdod", "phh2o", "soc", "nitrogen"]

        # SoilGrids REST API
        base_url = "https://rest.isric.org/soilgrids/v2.0/properties/query"
        
        # For actual implementation, would need to make multiple requests for each property
        # and depth combination, then mosaic the results
        
        result = {
            "status": "placeholder",
            "message": "SoilGrids download requires multiple API calls per property/depth. Use batch download.",
            "bbox": bbox,
            "properties": properties,
            "depth": depth,
            "api_base": base_url,
        }
        
        cache_name = f"soilgrids_{bbox[0]}_{bbox[1]}_{bbox[2]}_{bbox[3]}_{depth}"
        self.cache_geojson(cache_name, result)
        
        return result

    async def download_india_wris_groundwater(
        self,
        state: str,
        district: Optional[str] = None,
    ) -> dict:
        """
        Download groundwater data from India-WRIS.
        Note: Requires authentication.
        """
        result = {
            "status": "placeholder",
            "message": "India-WRIS requires registration and authentication.",
            "state": state,
            "district": district,
            "api_base": "https://india-wris.gov.in/api",
        }
        
        cache_name = f"india_wris_gw_{state}_{district or 'all'}_{datetime.datetime.now().strftime('%Y%m%d')}"
        self.cache_geojson(cache_name, result)
        
        return result

    async def download_rainfall_forecast(
        self,
        region: dict,  # GeoJSON geometry or bbox
        source: str = "open-meteo",
        days: int = 7,
    ) -> dict:
        """Download rainfall forecast for a region."""
        # Extract centroid for point forecast
        if region.get("type") == "Polygon":
            coords = region["coordinates"][0]
            lon = sum(c[0] for c in coords) / len(coords)
            lat = sum(c[1] for c in coords) / len(coords)
        elif region.get("type") == "Point":
            lon, lat = region["coordinates"]
        else:
            # Assume bbox [min_lon, min_lat, max_lon, max_lat]
            lon = (region[0] + region[2]) / 2
            lat = (region[1] + region[3]) / 2

        if source == "open-meteo":
            return await self.download_open_meteo_forecast(lat, lon, days)
        elif source == "nasa-power":
            end_date = datetime.datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
            return await self.download_nasa_power(lat, lon, start_date, end_date)
        else:
            raise ValueError(f"Unsupported source: {source}")


class ScheduledRefreshService:
    """Service for scheduled forecast refresh and risk recomputation."""

    def __init__(self, refresh_interval_minutes: int = 60):
        self.refresh_interval = refresh_interval_minutes
        self.last_refresh: Optional[datetime.datetime] = None
        self.running = False
        self.data_ingestion = DataIngestionService()

    def start(self):
        """Start the scheduled refresh loop."""
        self.running = True
        self.last_refresh = datetime.datetime.now()
        logger.info(f"Scheduled refresh started every {self.refresh_interval} minutes")

    def stop(self):
        """Stop the scheduled refresh loop."""
        self.running = False
        logger.info("Scheduled refresh stopped")

    def should_refresh(self) -> bool:
        """Check if enough time has passed since last refresh."""
        if self.last_refresh is None:
            return True
        elapsed = datetime.datetime.now() - self.last_refresh
        return elapsed.total_seconds() >= (self.refresh_interval * 60)

    def record_refresh(self):
        """Record that a refresh just occurred."""
        self.last_refresh = datetime.datetime.now()

    def get_status(self) -> dict:
        """Get the current refresh status."""
        return {
            "running": self.running,
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
            "minutes_until_next": max(0, self.refresh_interval -
                (datetime.datetime.now() - self.last_refresh).seconds / 60) if self.last_refresh else self.refresh_interval,
        }

    async def refresh_forecast_for_region(self, region: dict, source: str = "open-meteo") -> dict:
        """Refresh forecast data for a region."""
        try:
            data = await self.data_ingestion.download_rainfall_forecast(region, source)
            self.record_refresh()
            return {"status": "success", "data": data}
        except Exception as e:
            logger.error(f"Forecast refresh failed: {e}")
            return {"status": "error", "error": str(e)}


class DataSourceRegistry:
    """Registry of available data sources and their accessibility."""

    def __init__(self):
        self.sources = {
            "open-meteo": {
                "base_url": "https://api.open-meteo.com/v1",
                "endpoints": ["forecast", "archive", "historical"],
                "requires_api_key": False,
                "free_tier": True,
                "description": "Global weather forecast and historical data (ERA5)",
            },
            "nasapower": {
                "base_url": "https://power.larc.nasa.gov/api/timing",
                "endpoints": ["hourly", "daily"],
                "requires_api_key": False,
                "free_tier": True,
                "description": "NASA POWER meteorological and solar data",
            },
            "gpm-imerg": {
                "base_url": "https://gpm.nasa.gov/data/imerg",
                "endpoints": ["early-run", "final-run"],
                "requires_api_key": False,
                "free_tier": True,
                "note": "Satellite rainfall - 0.1° resolution",
                "description": "GPM IMERG precipitation estimates",
            },
            "copernicus-dem": {
                "base_url": "https://www.eea.europa.eu/data-and-maps/data/copernicus-digital-elevation-model",
                "endpoints": ["download"],
                "requires_api_key": False,
                "free_tier": True,
                "note": "30m resolution DEM",
                "description": "Copernicus Digital Elevation Model (GLO-30)",
            },
            "esa-worldcover": {
                "base_url": "https://www.esa-worldcover.org/",
                "endpoints": ["download"],
                "requires_api_key": False,
                "free_tier": True,
                "note": "10m resolution land cover",
                "description": "ESA WorldCover 10m land cover classification",
            },
            "openstreetmap": {
                "base_url": "https://www.openstreetmap.org",
                "endpoints": ["export", "overpass"],
                "requires_api_key": False,
                "free_tier": True,
                "description": "OpenStreetMap vector data via Overpass API",
            },
            "isric-soilgrids": {
                "base_url": "https://rest.isric.org/soilgrids/v2.0",
                "endpoints": ["properties", "query"],
                "requires_api_key": False,
                "free_tier": True,
                "note": "250m resolution soil properties",
                "description": "ISRIC SoilGrids global soil property maps",
            },
            "india-wris": {
                "base_url": "https://india-wris.gov.in",
                "endpoints": ["groundwater", "flood-records", "reservoirs"],
                "requires_api_key": True,
                "free_tier": False,
                "note": "India-specific groundwater and flood data",
                "description": "India Water Resources Information System",
            },
        }

    def get_source_info(self, source_name: str) -> Optional[dict]:
        """Get information about a data source."""
        return self.sources.get(source_name)

    def list_available_sources(self) -> list:
        """List all registered data sources."""
        return list(self.sources.keys())


# Global instances
data_ingestion_service = DataIngestionService()
scheduled_refresh_service = ScheduledRefreshService()
data_source_registry = DataSourceRegistry()