from flask_login import UserMixin
from db import get_connection
from flask_bcrypt import Bcrypt

bcrypt = Bcrypt()


class User(UserMixin):
    def __init__(self, id, username, role='viewer',
                 allowed_tables=None):
        self.id             = id
        self.username       = username
        self.role           = role
        self.allowed_tables = allowed_tables or []

    def is_admin(self):
        return self.role == 'admin'

    def is_analyst(self):
        return self.role in ['admin', 'analyst']

    def can_upload(self):
        perms = get_role_permissions(self.role)
        return perms.get('can_upload', False)

    def can_access_table(self, table_name):
        if self.role == 'admin':
            return True
        perms = get_role_permissions(self.role)
        if not perms.get('can_query', False):
            return False
        if self.role == 'analyst':
            return True
        # Viewer — check allowed tables
        if not self.allowed_tables:
            return False
        return table_name.lower() in [
            t.lower() for t in self.allowed_tables
        ]

    def get_allowed_tables_list(self):
        if self.role in ['admin', 'analyst']:
            return []
        return self.allowed_tables


def get_role_permissions(role_name):
    """Get permissions for a role from DB"""
    try:
        conn   = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM roles WHERE name = %s",
            (role_name,)
        )
        role = cursor.fetchone()
        cursor.close()
        conn.close()
        if role:
            return role
        return {
            'can_upload': False,
            'can_query':  True,
            'is_admin':   False
        }
    except Exception:
        return {
            'can_upload': False,
            'can_query':  True,
            'is_admin':   False
        }


def build_user_object(user_data):
    if not user_data:
        return None

    allowed = []
    if user_data.get('allowed_tables'):
        allowed = [
            t.strip()
            for t in user_data['allowed_tables'].split(',')
            if t.strip()
        ]

    return User(
        id             = user_data['id'],
        username       = user_data['username'],
        role           = user_data.get('role', 'viewer'),
        allowed_tables = allowed
    )


def get_user_by_username(username):
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM users WHERE username = %s",
        (username,)
    )
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user


def get_user_by_id(user_id):
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM users WHERE id = %s",
        (user_id,)
    )
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user


def get_all_users():
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, username, role,
               allowed_tables, created_at
        FROM users
        ORDER BY created_at DESC
    """)
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return users


def get_all_roles():
    """Get all roles from DB"""
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM roles ORDER BY name")
    roles = cursor.fetchall()
    cursor.close()
    conn.close()
    return roles


def create_role(name, description,
                can_upload=False, can_query=True):
    """Admin creates a new role"""
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO roles
            (name, description, can_upload, can_query)
            VALUES (%s, %s, %s, %s)
        """, (name.lower(), description,
              can_upload, can_query))
        conn.commit()
        return True
    except Exception as e:
        print(f"[Auth] Create role error: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def delete_role(role_name):
    """Admin deletes a role"""
    # Cannot delete built-in roles
    if role_name in ['admin', 'analyst', 'viewer']:
        return False, "Cannot delete built-in roles"
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM roles WHERE name = %s",
            (role_name,)
        )
        conn.commit()
        return True, "Role deleted"
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()


def create_user(username, password, role='viewer'):
    hashed = bcrypt.generate_password_hash(
        password).decode('utf-8')
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users "
            "(username, password_hash, role) "
            "VALUES (%s, %s, %s)",
            (username, hashed, role)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[Auth] Error: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def update_user(user_id, role, allowed_tables=None):
    """Update user role and table access"""
    tables_str = None
    if allowed_tables:
        if isinstance(allowed_tables, list):
            tables_str = ','.join(allowed_tables)
        else:
            tables_str = allowed_tables

    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE users
            SET role = %s, allowed_tables = %s
            WHERE id = %s
        """, (role, tables_str, user_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"[Auth] Update error: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def delete_user(user_id):
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM users WHERE id = %s",
            (user_id,)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[Auth] Delete error: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def revoke_access(user_id):
    """Remove all table access from viewer"""
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE users
            SET allowed_tables = NULL
            WHERE id = %s
        """, (user_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"[Auth] Revoke error: {e}")
        return False
    finally:
        cursor.close()
        conn.close()