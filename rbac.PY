from functools import wraps
from flask import jsonify, redirect, url_for, flash
from flask_login import current_user


def admin_required(f):
    """
    Decorator — only admins can access this route.
    Usage: @admin_required
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if not current_user.is_admin():
            flash("Admin access required.", "error")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


def analyst_required(f):
    """
    Decorator — analysts and admins can access.
    Usage: @analyst_required
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if not current_user.is_analyst():
            flash("Analyst access required.", "error")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


def filter_schema_for_user(schema, user):
    """
    Filter schema to only show tables
    the user is allowed to access.
    Viewers only see their allowed tables.
    """
    if user.role in ['admin', 'analyst']:
        return schema  # Full schema

    # For viewers filter the schema
    allowed = user.get_allowed_tables_list()
    if not allowed:
        return "No tables assigned to your account."

    lines        = schema.split('\n\n')
    filtered     = []
    current_table = None

    for block in lines:
        for table in allowed:
            if f"Table: {table}" in block:
                filtered.append(block)
                break

    return '\n\n'.join(filtered) if filtered else \
           "No accessible tables found."


def check_table_access(user, sql_query):
    """
    Check if user's SQL query only accesses
    tables they're allowed to see.
    Returns (allowed, reason)
    """
    if user.role in ['admin', 'analyst']:
        return True, "Full access"

    allowed = user.get_allowed_tables_list()
    if not allowed:
        return False, "No tables assigned to your account"

    sql_upper = sql_query.upper()

    # Check FROM and JOIN clauses
    import re
    pattern = r'\b(?:FROM|JOIN)\s+(\w+)'
    tables_used = re.findall(pattern, sql_upper)

    for table in tables_used:
        table_lower = table.lower()
        if table_lower not in [t.lower() for t in allowed]:
            return (
                False,
                f"You don't have access to table: {table_lower}"
            )

    return True, "Access granted"
