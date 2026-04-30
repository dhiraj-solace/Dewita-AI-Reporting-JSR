import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pathlib import Path
from .db_to_schma import get_mysql_schema_json
from .schema_validator import SchemaValidationError, validate_schema_catalog

class SchemaService:
    def __init__(self, cache_dir: str = None):
        self.cache_dir = Path(cache_dir or os.path.join(os.path.dirname(__file__), '..', 'data'))
        self.cache_file = self.cache_dir / 'schema_cache.json'
        self.static_schema_file = self.cache_dir / 'schema_catalog.json'
        
    def _is_cache_valid(self, cache_data: Dict[str, Any]) -> bool:
        if not cache_data.get('fetched_at'):
            return False
        
        try:
            fetched_at = datetime.fromisoformat(cache_data['fetched_at'])
            return datetime.now() - fetched_at < timedelta(hours=24)
        except (ValueError, TypeError):
            return False
    
    def _load_cached_schema(self, allow_stale: bool = False) -> Optional[Dict[str, Any]]:
        if not self.cache_file.exists():
            return None
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            if allow_stale or self._is_cache_valid(cache_data):
                return cache_data
        except (json.JSONDecodeError, IOError):
            pass
        
        return None
    
    def _save_cached_schema(self, schema_data: Dict[str, Any]) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(schema_data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"Warning: Could not save schema cache: {e}")

    def _schema_is_usable(self, schema_data: Dict[str, Any]) -> bool:
        try:
            validate_schema_catalog(schema_data)
            return True
        except SchemaValidationError:
            return False
    
    def _load_static_schema(self) -> Optional[Dict[str, Any]]:
        if not self.static_schema_file.exists():
            return None
        
        try:
            with open(self.static_schema_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    
    def _convert_to_catalog_format(self, live_schema: Dict[str, Any]) -> Dict[str, Any]:
        static_schema = self._load_static_schema() or {}
        
        catalog = {
            "source_files": ["live_database"],
            "fetched_at": live_schema.get('fetched_at'),
            "notes": [
                "Schema fetched from live database",
                f"Last updated: {live_schema.get('fetched_at', 'Unknown')}",
                "Static schema metadata preserved where available"
            ],
            "relationships": [],
            "tables": []
        }
        
        for table_name, table_data in live_schema.get('tables', {}).items():
            table_info = {
                "name": table_name,
                "columns": []
            }
            
            static_table = next((t for t in static_schema.get('tables', []) if t.get('name') == table_name), None)
            if static_table:
                table_info["description"] = static_table.get('description', '')
                table_info["aliases"] = static_table.get('aliases', [])
            else:
                table_info["description"] = table_data.get('description', '')
                table_info["aliases"] = []
            
            for col in table_data.get('columns', []):
                col_info = {
                    "name": col['column_name'],
                    "type": col['data_type']
                }
                
                if static_table:
                    static_col = next((c for c in static_table.get('columns', []) if c.get('name') == col['column_name']), None)
                    if static_col:
                        col_info["description"] = static_col.get('description', '')
                    else:
                        col_info["description"] = col.get('column_comment', '') or ''
                else:
                    col_info["description"] = col.get('column_comment', '') or ''
                
                table_info["columns"].append(col_info)
            
            catalog["tables"].append(table_info)
        
        for rel in live_schema.get('relationships', []):
            catalog["relationships"].append({
                "from": f"{rel['table_name']}.{rel['column_name']}",
                "to": f"{rel['referenced_table_name']}.{rel['referenced_column_name']}",
                "type": "many_to_one"
            })
        
        return catalog

    def _fetch_live_schema_with_retry(self, attempts: int = 3) -> Dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                live_schema = get_mysql_schema_json()
                if 'error' in live_schema:
                    raise Exception(f"Database error: {live_schema['error']}")
                return live_schema
            except Exception as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(0.25 * attempt)
        raise Exception(f"Live schema fetch failed after {attempts} attempts: {last_error}") from last_error
    
    def get_schema(self, force_refresh: bool = False) -> Dict[str, Any]:
        if not force_refresh:
            cached_schema = self._load_cached_schema()
            if cached_schema and self._schema_is_usable(cached_schema):
                return cached_schema
        
        try:
            live_schema = self._fetch_live_schema_with_retry()
            catalog_format = self._convert_to_catalog_format(live_schema)
            validate_schema_catalog(catalog_format)
            self._save_cached_schema(catalog_format)
            return catalog_format
            
        except Exception as e:
            print(f"Warning: Could not fetch live schema: {e}")
            
            fallback_schema = self._load_cached_schema(allow_stale=True)
            if fallback_schema and self._schema_is_usable(fallback_schema):
                return fallback_schema
            
            static_schema = self._load_static_schema()
            if static_schema and self._schema_is_usable(static_schema):
                return static_schema
            
            raise Exception("No schema available: live fetch failed, no cache, no static fallback")
    
    def refresh_schema(self) -> Dict[str, Any]:
        return self.get_schema(force_refresh=True)

schema_service = SchemaService()
