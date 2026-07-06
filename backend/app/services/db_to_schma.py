from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy import create_engine, text
from app.core.config import get_settings

def get_db_config() -> Dict[str, Any]:
    settings = get_settings()
    if not settings.resolved_database_url or not settings.db_name:
        raise ValueError("Missing required database credentials in environment variables")
    return {"database_url": settings.resolved_database_url, "database": settings.db_name}

def get_mysql_schema_json(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if config is None:
        config = get_db_config()

    engine = create_engine(config["database_url"], pool_pre_ping=True, pool_recycle=280)
    try:
        schema_data: dict[str, Any] = {}
        database_name = config["database"]

        with engine.connect() as conn:
            tables = [
                row.table_name
                for row in conn.execute(
                    text(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = :database_name
                        ORDER BY table_name
                        """
                    ),
                    {"database_name": database_name},
                )
            ]

            for table in tables:
                columns = [
                    dict(row._mapping)
                    for row in conn.execute(
                        text(
                            """
                            SELECT
                              column_name,
                              data_type,
                              column_type,
                              is_nullable,
                              column_default,
                              character_maximum_length,
                              numeric_precision,
                              ordinal_position
                            FROM information_schema.columns
                            WHERE table_schema = :database_name AND table_name = :table_name
                            ORDER BY ordinal_position
                            """
                        ),
                        {"database_name": database_name, "table_name": table},
                    )
                ]

                foreign_keys = [
                    dict(row._mapping)
                    for row in conn.execute(
                        text(
                            """
                            SELECT column_name, referenced_table_name, referenced_column_name
                            FROM information_schema.key_column_usage
                            WHERE table_schema = :database_name
                              AND table_name = :table_name
                              AND referenced_table_name IS NOT NULL
                            """
                        ),
                        {"database_name": database_name, "table_name": table},
                    )
                ]

                schema_data[table] = {"columns": columns, "foreign_keys": foreign_keys}

            relationships = [
                dict(row._mapping)
                for row in conn.execute(
                    text(
                        """
                        SELECT table_name, column_name, referenced_table_name, referenced_column_name
                        FROM information_schema.key_column_usage
                        WHERE table_schema = :database_name
                          AND referenced_table_name IS NOT NULL
                        """
                    ),
                    {"database_name": database_name},
                )
            ]

        return {
            'tables': schema_data,
            'relationships': relationships,
            'database_name': database_name,
            'fetched_at': datetime.now().isoformat()
        }

    except Exception as err:
        return {"error": str(err), "timestamp": datetime.now().isoformat()}

def get_mysql_schema_json_legacy(config: Optional[Dict[str, Any]] = None) -> str:
    import json
    schema = get_mysql_schema_json(config)
    return json.dumps(schema, indent=4)
