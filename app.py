from flask import (Flask, request, jsonify, render_template,
                   redirect, url_for, flash, session)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from datetime import datetime
import json
import os
import time

from auth import (User, get_user_by_username, get_user_by_id,
                  create_user, bcrypt, get_all_users,
                  update_user, delete_user, build_user_object,
                  revoke_access)
from schema_generator import get_schema, get_table_list
from llm_chain import (generate_sql, explain_results,
                       generate_followup_questions,
                       process_question_complete)
from sql_executor import execute_sql
from scheduler import start_scheduler
from data_loader import load_csv_to_mysql
from relationship_detector import refresh_relationships
from memory import (save_message, get_history,
                    clear_history, get_all_conversations)
from local_engine import cache_get, cache_set, cache_clear
from rbac import (admin_required, analyst_required,
                  filter_schema_for_user, check_table_access)
from security import validator, audit

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
bcrypt.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

UPLOAD_FOLDER      = 'data'
ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() \
           in ALLOWED_EXTENSIONS


@login_manager.user_loader
def load_user(user_id):
    user_data = get_user_by_id(int(user_id))
    return build_user_object(user_data)


# ── Pages ──────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return render_template(
        "chat.html",
        username=current_user.username
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username  = request.form.get("username")
        password  = request.form.get("password")
        user_data = get_user_by_username(username)
        if user_data and bcrypt.check_password_hash(
                user_data['password_hash'], password):
            user = build_user_object(user_data)
            login_user(user)
            return redirect(url_for("index"))
        else:
            flash("Invalid credentials", "error")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        from db import get_connection
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        count  = cursor.fetchone()[0]
        cursor.close()
        conn.close()

        role    = 'admin' if count == 0 else 'viewer'
        success = create_user(username, password, role)

        if success:
            if role == 'admin':
                flash(
                    "Admin account created! You have full access.",
                    "success"
                )
            else:
                flash("Account created! Please log in.",
                      "success")
            return redirect(url_for("login"))
        else:
            flash("Username already exists.", "error")

    return render_template("register.html")


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if not current_user.is_analyst():
        flash("You don't have permission to upload files.")
        return redirect(url_for("index"))

    if request.method == "POST":
        if 'file' not in request.files:
            return jsonify({"error": "No file selected"}), 400

        file       = request.files['file']
        table_name = request.form.get(
            "table_name", "").strip().lower().replace(" ", "_")

        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400

        if not allowed_file(file.filename):
            return jsonify(
                {"error": "Only CSV and Excel files allowed"}
            ), 400

        if not table_name:
            table_name = secure_filename(file.filename)
            table_name = table_name.rsplit('.', 1)[0].lower()
            table_name = table_name.replace(
                "-", "_").replace(" ", "_")

        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filepath = os.path.join(
            UPLOAD_FOLDER, secure_filename(file.filename))
        file.save(filepath)

        success = load_csv_to_mysql(filepath, table_name)

        if success:
            refresh_relationships()
            cache_clear()
            return jsonify({
                "success": True,
                "message": f"Loaded into table '{table_name}'",
                "table":   table_name
            })
        else:
            return jsonify(
                {"error": "Failed to load file"}), 500

    return render_template("upload.html")


@app.route("/tables")
@login_required
def tables():
    return jsonify({"tables": get_table_list()})


@app.route("/clear_history", methods=["POST"])
@login_required
def clear_chat():
    clear_history(current_user.id)
    return jsonify({"status": "cleared"})


# ── Admin Routes ───────────────────────────────────────────────

@app.route("/admin")
@login_required
@admin_required
def admin_panel():
    from auth import get_all_roles
    users         = get_all_users()
    roles         = get_all_roles()
    conversations = get_all_conversations(limit=100)
    all_tables    = get_table_list()

    stats = {
        'total_users': len(users),
        'admins':      sum(1 for u in users
                           if u['role'] == 'admin'),
        'analysts':    sum(1 for u in users
                           if u['role'] == 'analyst'),
        'viewers':     sum(1 for u in users
                           if u['role'] == 'viewer'),
    }

    return render_template(
        "admin.html",
        users         = users,
        roles         = roles,
        conversations = conversations,
        all_tables    = all_tables,
        stats         = stats
    )


@app.route("/admin/create_user", methods=["POST"])
@login_required
@admin_required
def admin_create_user():
    username       = request.form.get("username")
    password       = request.form.get("password")
    role           = request.form.get("role", "viewer")
    allowed_tables = request.form.getlist("allowed_tables")

    success = create_user(username, password, role)

    if success and allowed_tables and role == 'viewer':
        from db import get_connection
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM users WHERE username = %s",
            (username,)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            update_user(
                row[0], role,
                ','.join(allowed_tables)
            )

    if success:
        flash(f"User '{username}' created as {role}!")
    else:
        flash(f"Username '{username}' already exists.")

    return redirect(url_for('admin_panel'))


@app.route("/admin/update_user", methods=["POST"])
@login_required
@admin_required
def admin_update_user():
    user_id        = request.form.get("user_id")
    role           = request.form.get("role")
    allowed_tables = request.form.getlist("allowed_tables")

    tables_str = ','.join(allowed_tables) \
                 if allowed_tables else None

    update_user(int(user_id), role, tables_str)
    flash("User updated successfully!")
    return redirect(url_for('admin_panel'))


@app.route("/admin/revoke_access", methods=["POST"])
@login_required
@admin_required
def admin_revoke_access():
    data    = request.get_json()
    user_id = data.get("user_id")
    revoke_access(int(user_id))
    return jsonify({"success": True})


@app.route("/admin/delete_user", methods=["POST"])
@login_required
@admin_required
def admin_delete_user():
    data    = request.get_json()
    user_id = data.get("user_id")
    delete_user(int(user_id))
    return jsonify({"success": True})


@app.route("/admin/create_role", methods=["POST"])
@login_required
@admin_required
def admin_create_role():
    from auth import create_role
    name        = request.form.get("name", "").lower()
    description = request.form.get("description", "")
    can_upload  = bool(request.form.get("can_upload"))
    can_query   = bool(request.form.get("can_query", True))

    success = create_role(
        name, description, can_upload, can_query)
    if success:
        flash(f"Role '{name}' created!")
    else:
        flash(f"Role '{name}' already exists.")

    return redirect(url_for('admin_panel'))


@app.route("/admin/delete_role", methods=["POST"])
@login_required
@admin_required
def admin_delete_role():
    from auth import delete_role
    data      = request.get_json()
    role_name = data.get("role_name")
    success, msg = delete_role(role_name)
    return jsonify({"success": success, "message": msg})


@app.route("/admin/audit")
@login_required
@admin_required
def audit_log():
    logs   = audit.get_logs(limit=200)
    report = audit.get_security_report()

    # Convert datetime objects for JSON
    clean_logs = []
    for log in logs:
        clean_log = dict(log)
        if clean_log.get('created_at'):
            clean_log['created_at'] = \
                clean_log['created_at'].strftime(
                    '%Y-%m-%d %H:%M:%S')
        clean_logs.append(clean_log)

    return jsonify({
        "logs":   clean_logs,
        "report": report
    })


# ── Chat Route ─────────────────────────────────────────────────

@app.route("/chat", methods=["POST"])
@login_required
def chat():
    data          = request.get_json()
    user_question = data.get("question", "").strip()

    if not user_question:
        return jsonify({"error": "Empty question"}), 400

    chat_history = get_history(current_user.id)
    start_time   = time.time()

    try:
        schema = get_schema()
        schema = filter_schema_for_user(schema, current_user)

        # ── STEP 1: Check cache ────────────────────────────────
        cached = cache_get(user_question)
        if cached:
            print(f"[App] Cache HIT — 0 API calls")
            followups = []
            try:
                followups = json.loads(
                    cached.get('followups', '[]') or '[]'
                )
            except Exception:
                followups = []

            return jsonify({
                "answer":    cached['answer'],
                "sql":       cached['sql_query'],
                "row_count": cached['row_count'],
                "intent":    "DATA_QUESTION",
                "followups": followups,
                "chart":     None,
                "badge":     "⚡ Instant",
                "protected": True
            })

        # ── STEP 2: One LLM call ───────────────────────────────
        print(f"[App] 1 LLM call for: {user_question}")
        llm_response = process_question_complete(
            user_question, schema, chat_history
        )

        intent          = llm_response.get(
            "intent", "DATA_QUESTION")
        sql_query       = llm_response.get("sql")
        casual_response = llm_response.get("casual_response")
        followups       = llm_response.get("followups", [])

        print(f"[App] Intent: {intent}")

        # ── STEP 3: Non-data intents ───────────────────────────
        if intent != "DATA_QUESTION":
            answer = casual_response or "How can I help you?"

            audit.log(
                current_user.id,
                current_user.username,
                current_user.role,
                None, 'success',
                response_ms = int(
                    (time.time() - start_time) * 1000),
                intent=intent
            )

            save_message(current_user.id, 'user', user_question)
            save_message(current_user.id, 'assistant', answer)

            return jsonify({
                "answer":    answer,
                "sql":       None,
                "row_count": 0,
                "intent":    intent,
                "followups": followups,
                "chart":     None,
                "badge":     "💬 1 call",
                "protected": True
            })

        # ── STEP 4: Validate SQL ───────────────────────────────
        if not sql_query:
            return jsonify({
                "answer":    "Couldn't generate query. "
                             "Please rephrase.",
                "sql":       None,
                "row_count": 0,
                "followups": followups,
                "chart":     None
            })

        is_valid, reason, sql_query = validator.validate(
            sql_query, current_user)

        if not is_valid:
            audit.log(
                current_user.id,
                current_user.username,
                current_user.role,
                sql_query, 'blocked',
                blocked_reason = reason,
                intent         = intent
            )
            return jsonify({
                "answer":    f"⛔ Query blocked: {reason}",
                "sql":       sql_query,
                "row_count": 0,
                "followups": followups,
                "chart":     None,
                "badge":     "🛡️ Blocked by Firewall"
            })

        # ── STEP 5: Check table access ─────────────────────────
        allowed, reason = check_table_access(
            current_user, sql_query)

        if not allowed:
            audit.log(
                current_user.id,
                current_user.username,
                current_user.role,
                sql_query, 'blocked',
                blocked_reason = reason,
                intent         = intent
            )
            return jsonify({
                "answer":    f"⛔ Access denied: {reason}",
                "sql":       None,
                "row_count": 0,
                "intent":    intent,
                "followups": [],
                "chart":     None,
                "badge":     "🔒 Access Denied"
            })

        # ── STEP 6: Execute SQL ────────────────────────────────
        result = execute_sql(sql_query)

        # ── STEP 7: Retry if failed ────────────────────────────
        if not result["success"]:
            print(f"[App] SQL failed — retrying...")
            retry_response = process_question_complete(
                f"SQL failed: {result['error']}. "
                f"Fix for: {user_question}",
                schema, chat_history
            )
            new_sql = retry_response.get("sql", sql_query)
            if new_sql:
                is_valid, reason, new_sql = \
                    validator.validate(new_sql, current_user)
                if is_valid:
                    allowed, _ = check_table_access(
                        current_user, new_sql)
                    if allowed:
                        sql_query = new_sql
                        result    = execute_sql(sql_query)

        if not result["success"]:
            audit.log(
                current_user.id,
                current_user.username,
                current_user.role,
                sql_query, 'failed',
                intent=intent
            )
            return jsonify({
                "answer":    "Sorry, couldn't execute. "
                             "Please try rephrasing.",
                "sql":       sql_query,
                "row_count": 0,
                "followups": followups,
                "chart":     None
            })

        # ── STEP 8: Format answer ──────────────────────────────
        answer = _format_simple_result(
            user_question,
            result["results"],
            result["columns"]
        )
        badge = "⚡ 1 call"

        if answer is None:
            answer = explain_results(
                user_question, sql_query,
                result["results"], result["columns"],
                chat_history
            )
            badge = "🤖 2 calls"

        # ── STEP 9: Chart ──────────────────────────────────────
        chart_data = _build_chart(
            user_question,
            result["results"],
            result["columns"]
        )

        # ── STEP 10: Audit log ─────────────────────────────────
        response_ms = int((time.time() - start_time) * 1000)
        audit.log(
            current_user.id,
            current_user.username,
            current_user.role,
            sql_query, 'success',
            row_count   = len(result["results"]),
            response_ms = response_ms,
            intent      = intent
        )

        # ── STEP 11: Cache + Memory ────────────────────────────
        cache_set(
            user_question, sql_query,
            answer, len(result["results"]),
            json.dumps(followups)
        )

        save_message(current_user.id, 'user', user_question)
        save_message(current_user.id, 'assistant', answer)

        print(f"[App] Done — {badge} — {response_ms}ms")

        return jsonify({
            "answer":    answer,
            "sql":       sql_query,
            "row_count": len(result["results"]),
            "intent":    intent,
            "followups": followups,
            "chart":     chart_data,
            "badge":     badge,
            "protected": True
        })

    except Exception as e:
        print(f"[App] Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


# ── Helpers ────────────────────────────────────────────────────

def _format_simple_result(question, results, columns):
    if not results:
        return "No data found."

    if len(results) == 1 and len(columns) == 1:
        val = results[0][0]
        col = columns[0].lower()
        try:
            num = float(val)
            if any(w in col for w in
                   ['revenue', 'sales', 'total', 'amount']):
                formatted = f"${num:,.2f}"
                if num >= 1_000_000_000:
                    formatted += f" ({num/1_000_000_000:.1f}B)"
                elif num >= 1_000_000:
                    formatted += f" ({num/1_000_000:.1f}M)"
                return f"The total is **{formatted}**."
            if any(w in col for w in ['count', 'orders']):
                return f"There are **{int(num):,}** total."
            if any(w in col for w in ['avg', 'average']):
                return f"The average is **${num:,.2f}**."
            return f"The result is **{num:,.2f}**."
        except (ValueError, TypeError):
            return f"Result: **{val}**"

    return None


def _build_chart(question, results, columns):
    if not results or len(results) < 2:
        return None
    if len(columns) < 2:
        return None

    q = question.lower()

    if any(w in q for w in [
        'trend', 'monthly', 'yearly', 'over time',
        'by month', 'by year', 'daily', 'weekly'
    ]):
        chart_type = 'line'
    elif any(w in q for w in [
        'breakdown', 'distribution', 'percentage',
        'share', 'split', 'proportion'
    ]):
        chart_type = 'pie'
    else:
        chart_type = 'bar'

    results = results[:20]
    labels  = [str(row[0]) for row in results]
    values  = []

    for row in results:
        try:
            values.append(round(float(row[1]), 2))
        except (ValueError, TypeError):
            values.append(0)

    colors = [
        'rgba(99,  179, 237, 0.85)',
        'rgba(72,  187, 120, 0.85)',
        'rgba(246, 173, 85,  0.85)',
        'rgba(237, 100, 166, 0.85)',
        'rgba(154, 117, 234, 0.85)',
        'rgba(56,  178, 172, 0.85)',
        'rgba(229, 62,  62,  0.85)',
        'rgba(49,  130, 206, 0.85)',
    ]

    bg     = [colors[i % len(colors)]
               for i in range(len(values))]
    border = [c.replace('0.85', '1') for c in bg]

    dataset = {
        "label":           columns[1],
        "data":            values,
        "backgroundColor": bg,
        "borderColor":     border,
        "borderWidth":     2,
    }

    if chart_type == 'line':
        dataset.update({
            "fill":    False,
            "tension": 0.4
        })

    return {
        "type": chart_type,
        "data": {
            "labels":   labels,
            "datasets": [dataset]
        },
        "options": {
            "responsive":          True,
            "maintainAspectRatio": False,
            "plugins": {
                "legend": {
                    "labels": {"color": "#e2e8f0"}
                }
            },
            "scales": {} if chart_type == 'pie' else {
                "x": {
                    "ticks": {"color": "#94a3b8"},
                    "grid":  {"color": "#1e293b"}
                },
                "y": {
                    "ticks":       {"color": "#94a3b8"},
                    "grid":        {"color": "#334155"},
                    "beginAtZero": True
                }
            }
        }
    }


if __name__ == "__main__":
    start_scheduler()
    app.run(debug=True)