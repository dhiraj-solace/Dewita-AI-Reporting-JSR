#!/usr/bin/env python3
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parents[2]))

from app.services.schema_service import schema_service

def main():
    try:
        print("Fetching fresh schema from database...")
        schema = schema_service.refresh_schema()
        
        print(f"Successfully updated schema with {len(schema.get('tables', []))} tables")
        print(f"Schema cached at: {schema_service.cache_file}")
        print("Next automatic refresh: 24 hours")
        
    except Exception as e:
        print(f"Error updating schema: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
