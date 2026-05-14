from db import get_connection
from relationship_detector import (
    get_relationships,
    format_relationships_for_llm
)

HIDDEN_TABLES = [
    'users', 'conversations', 'roles',
    'sales_orders_old', '_loaded_files',
    '_relationships', '_query_cache'
]


def get_schema():
    """
    Returns STRUCTURE ONLY schema.
    Zero actual data values sent.
    Safe to send to any LLM.
    """
    conn   = get_connection()
    cursor = conn.cursor()

    cursor.execute("SHOW TABLES")
    tables = [
        row[0] for row in cursor.fetchall()
        if row[0] not in HIDDEN_TABLES
        and not row[0].startswith('_')
    ]

    schema_parts = []

    for table in tables:
        cursor.execute(f"DESCRIBE `{table}`")
        columns = cursor.fetchall()

        # Build column info — types only, no values
        col_info = []
        for col in columns:
            col_name = col[0]
            col_type = col[1].upper()

            # Simplify type for LLM understanding
            if 'INT' in col_type:
                simple_type = 'INTEGER'
            elif 'FLOAT' in col_type or \
                 'DOUBLE' in col_type or \
                 'DECIMAL' in col_type:
                simple_type = 'DECIMAL'
            elif 'DATE' in col_type or \
                 'TIME' in col_type:
                simple_type = 'DATETIME'
            elif 'TEXT' in col_type or \
                 'CHAR' in col_type or \
                 'VARCHAR' in col_type:
                simple_type = 'TEXT'
            else:
                simple_type = 'TEXT'

            col_info.append(f"{col_name} ({simple_type})")

        schema_parts.append(
            f"Table: {table}\n"
            f"Columns: {', '.join(col_info)}"
        )

    cursor.close()
    conn.close()

    # Add relationships
    relationships    = get_relationships()
    relationship_str = format_relationships_for_llm(
        relationships)

    full_schema = "\n\n".join(schema_parts)
    full_schema += f"\n\n{relationship_str}"

    return full_schema


def get_table_list():
    """Returns table names and row counts for UI only"""
    conn   = get_connection()
    cursor = conn.cursor()

    cursor.execute("SHOW TABLES")
    tables = [
        row[0] for row in cursor.fetchall()
        if row[0] not in HIDDEN_TABLES
        and not row[0].startswith('_')
    ]

    table_info = []
    for table in tables:
        cursor.execute(
            f"SELECT COUNT(*) FROM `{table}`")
        count = cursor.fetchone()[0]
        table_info.append({
            "name": table,
            "rows": count
        })

    cursor.close()
    conn.close()
    return table_info