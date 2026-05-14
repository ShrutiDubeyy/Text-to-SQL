from db import get_connection

def execute_sql(sql_query):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(sql_query)
        results = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        return {"success": True, "results": results, "columns": columns}

    except Exception as e:
        return {"success": False, "error": str(e), "results": [], "columns": []}

    finally:
        cursor.close()
        conn.close()