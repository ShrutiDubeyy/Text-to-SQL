# Text-to-SQL Data Analyst Chatbot

An enterprise-grade AI-powered data analyst platform that converts natural language questions into SQL queries, executes them on a MySQL database, and returns plain English answers with auto-generated visualizations. Built with a security-first architecture where real data never reaches any third-party AI service.

---

## Table of Contents

1. [What This System Does](#what-this-system-does)
2. [Architecture Overview](#architecture-overview)
3. [Component Deep Dive](#component-deep-dive)
4. [Library Explanations](#library-explanations)
5. [Security Architecture](#security-architecture)
6. [Data Flow — Step by Step](#data-flow)
7. [Analytics Engine](#analytics-engine)
8. [RAG System](#rag-system)
9. [Live Data Sync](#live-data-sync)
10. [Role Based Access Control](#role-based-access-control)
11. [Performance Optimization](#performance-optimization)
12. [Local LLM Architecture](#local-llm-architecture)
13. [Setup & Installation](#setup--installation)
14. [Docker Deployment](#docker-deployment)
15. [Tech Stack Summary](#tech-stack-summary)

---

## What This System Does

A non-technical business user types: *"What is the total revenue by channel this month?"*

The system:
1. Understands the intent using LLaMA 3.3 70B
2. Generates the correct MySQL query
3. Validates the query through a security firewall
4. Executes it on your private MySQL database
5. Returns a plain English explanation
6. Auto-generates a pie or bar chart
7. Suggests three follow-up questions
8. Logs the query metadata (not the data) for compliance

All of this happens in under 2 seconds. Real data never leaves your server.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                         │
│   CSV/Excel │ Google Sheets │ Webhook │ Upload UI           │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                     DATA PIPELINE                           │
│   data_loader.py → Pandas → SQLAlchemy → MySQL              │
│   auto_indexer.py → Column analysis → Index creation        │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   MYSQL DATABASE                            │
│   Business tables │ System tables │ Cache │ Audit log       │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              SCHEMA INTELLIGENCE LAYER                      │
│   schema_generator.py → Structure only (no values)          │
│   relationship_detector.py → LLM-based JOIN detection       │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                SECURITY LAYER (data_shield.py)              │
│   Layer 1: Real values never sent to LLM                    │
│   Layer 2: Context wiped after every response               │
│   Layer 3: Schema anonymized before transmission            │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              LLM PIPELINE (llm_chain.py)                    │
│   RAG context injection → Single JSON prompt                │
│   Returns: intent + sql + response + followups              │
└──────────┬──────────────────────────────┬───────────────────┘
           │                              │
           ▼                              ▼
┌──────────────────┐            ┌─────────────────────┐
│   Ollama Local   │            │    Groq API Cloud   │
│   LLaMA 3.1      │            │    LLaMA 3.3 70B    │
│   Zero exposure  │            │    Schema only      │
└──────────────────┘            └─────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│              SQL FIREWALL (security.py)                     │
│   Validates query │ Blocks dangerous patterns               │
│   Checks table permissions │ Enforces RBAC                  │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│           SQL EXECUTOR + OPTIMIZER (optimizer.py)           │
│   Timeout protection │ Pagination │ Performance tracking    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    OUTPUT LAYER                             │
│   Plain English explanation │ Chart.js visualization        │
│   Memory saved to MySQL │ Audit log entry                   │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   USER INTERFACE                            │
│   chat.html │ dashboard.html │ admin.html │ sync.html       │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Deep Dive

### app.py — The Orchestrator

`app.py` is the central nervous system of the entire application. It is a Flask web application that handles every HTTP request and coordinates all other modules.

**What it does:**
- Registers all URL routes (chat, admin, dashboard, sync, reports, webhooks)
- Enforces authentication on every protected route using Flask-Login decorators
- Orchestrates the full question-answering pipeline in the `/chat` route
- Handles file uploads, user management, and report generation
- Starts the background scheduler on application boot
- Runs the auto-indexer on startup to ensure all tables are indexed

**The chat pipeline inside app.py:**

When a user submits a question, the `/chat` route executes this exact sequence:

```
1. Check query cache → if hit, return instantly (0 API calls)
2. Load conversation history from MySQL
3. Get database schema (structure only)
4. Filter schema based on user's role permissions
5. Call process_question_complete() → single LLM call
6. Parse intent from LLM response
7. If not DATA_QUESTION → return casual response
8. Validate SQL through firewall
9. Check table-level permissions
10. Execute SQL with timeout protection
11. If failed → retry with error context
12. Format result as plain English
13. Build chart data if applicable
14. Save to query cache
15. Save to conversation memory
16. Write to audit log (metadata only)
17. Return JSON response to browser
```

Every step has error handling. If the LLM generates invalid SQL, the system retries once with the error message as context.

---

### llm_chain.py — The AI Brain

This module manages all communication with the language model. The most important architectural decision here is the **single prompt strategy**.

**The problem with multiple LLM calls:**

Early versions made four separate API calls per question:
- Call 1: What is the user's intent?
- Call 2: Generate the SQL query
- Call 3: Explain the results
- Call 4: Suggest follow-up questions

This meant 4x the cost, 4x the latency, and 4x the data exposure.

**The solution — structured JSON output:**

A single prompt asks the LLM to return all four pieces of information as a JSON object:

```json
{
  "intent": "DATA_QUESTION",
  "sql": "SELECT channel, SUM(line_total) FROM sales_order GROUP BY channel",
  "casual_response": null,
  "followups": ["Which channel grew most?", "Compare to last month", "Top products per channel"]
}
```

The LLM is instructed to return only this JSON. The system parses it and routes accordingly. This reduces API calls by 75% and cuts response time in half.

**The fallback chain:**

```
Primary:   llama-3.3-70b-versatile (Groq)
Fallback1: llama-3.1-8b-instant (Groq)
Fallback2: gemma2-9b-it (Groq)
Local:     llama3.1 via Ollama (localhost:11434)
```

If the primary model fails, the system automatically retries with the next model. If all cloud models fail and Ollama is running locally, it uses the local model.

---

### schema_generator.py — What the LLM Sees

This module is responsible for one critical task: generating a description of the database structure that is safe to send to the LLM.

**What it includes:**
- Table names
- Column names
- Column data types (simplified to INTEGER, DECIMAL, TEXT, DATETIME)
- Detected relationships between tables

**What it deliberately excludes:**
- Row counts
- Sample data values
- Actual business data of any kind

A real example of what gets sent to the LLM:

```
Table: sales_order
Columns: ordernumber (TEXT), quantityordered (INTEGER),
         line_total (DECIMAL), orderdate (DATETIME),
         channel (TEXT), warehouse_code (TEXT),
         customer_name_index (TEXT),
         product_description_index (TEXT)

Table: customers
Columns: customer_index (TEXT), customer_name (TEXT),
         city (TEXT), country (TEXT)

Relationships:
sales_order.customer_name_index → customers.customer_index
sales_order.product_description_index → products.product_index
```

The LLM has everything it needs to write correct SQL. It has nothing it should not have.

---

### relationship_detector.py — Automatic JOIN Discovery

When a new dataset is uploaded, the system does not know how tables relate to each other. This module solves that problem automatically.

**How it works:**

1. Extracts column names from all tables in the database
2. Sends only the column names (never values) to the LLM
3. Asks the LLM: "Based on these column names, which columns likely join to which?"
4. LLM identifies patterns like `customer_id` → `customers.id`
5. Results are cached in the `_relationships` MySQL table
6. Relationships are included in every schema sent to the LLM

**Why this matters:**

Without relationship detection, a question like "show revenue by customer city" would fail because the system would not know to JOIN `sales_order` with `customers`. With this module, multi-table queries work automatically on any uploaded dataset.

---

### data_shield.py — Three Layers of Data Protection

This is the security module that ensures real business data never reaches any third-party AI service.

**Layer 1 — Never send real values to LLM:**

Before sending schema to the LLM, all sample row values are replaced with type placeholders:

```
Before (unsafe):
{'customer_name': 'Raj Kumar', 'revenue': 5000000}

After (safe):
{'customer_name': '[TEXT]', 'revenue': '[NUMBER]'}
```

Sensitive column patterns (email, password, phone, SSN) are replaced with `[REDACTED]` entirely.

**Layer 2 — Stateless prompts:**

Every prompt sent to the LLM includes a privacy header instructing it to treat the session as isolated and not retain any information. After the response is received, the prompt variables are explicitly deleted from Python memory and garbage collection is forced.

```python
del secure_prompt
del safe_schema
import gc
gc.collect()
```

**Layer 3 — Schema anonymization:**

The schema generator only sends column names and types. No row counts, no sample values, no business context that could reveal sensitive information.

---

### security.py — SQL Firewall and Audit Logger

**QueryValidator — The SQL Firewall:**

Every SQL query generated by the LLM is intercepted here before it touches the database. The validator checks:

- Query must start with SELECT (no INSERT, UPDATE, DELETE, DROP)
- No dangerous keywords: DROP, DELETE, TRUNCATE, ALTER, CREATE, EXEC, UNION, INTO, OUTFILE
- No SQL injection patterns: comments (`--`, `/*`), multiple statements separated by semicolons
- No access to forbidden system tables: users, conversations, roles, audit logs
- Adds LIMIT clause if missing on non-aggregate queries

If any check fails, the query is blocked, the reason is logged, and the user sees an error message. The blocked attempt is recorded in the audit log.

**AuditLogger — Zero-Knowledge Compliance Logging:**

Every query is logged, but crucially, the log contains zero actual data. It records:

- Who asked (user ID and username)
- What role they have (admin, analyst, viewer)
- What type of query it was (aggregation, join, filtered, simple)
- Which tables were accessed
- How many rows were returned
- How long it took in milliseconds
- Whether it succeeded or was blocked
- If blocked, why it was blocked

It does NOT record:
- The actual question text
- The answer text
- Any data values from the results

This makes the audit log GDPR-compliant. A data breach of the audit log reveals zero business information.

---

### analytics_engine.py — Pure Python Data Science

This module replaces the LLM for all analytical calculations. Real data analysis does not need an AI to calculate averages and standard deviations. This is pure mathematics.

**Revenue calculations:**
Uses direct MySQL aggregate queries. `SUM(line_total)` for revenue, `COUNT(*)` for orders, `AVG(line_total)` for average order value. Filtered by date ranges using MySQL date functions.

**Anomaly Detection — Z-Score Algorithm:**

The system collects 30 days of daily revenue data, calculates the mean and standard deviation, then computes a z-score for each day:

```
z_score = (daily_revenue - mean_revenue) / std_deviation
```

A z-score above 2 or below -2 means the value is more than 2 standard deviations from normal. This is statistically unusual and flagged as an anomaly. This is the same algorithm used in real-world fraud detection and quality control systems.

**Forecasting — Linear Regression:**

The forecast uses the least squares method to fit a trend line through historical monthly revenue:

```
slope = Σ((x - x_mean)(y - y_mean)) / Σ((x - x_mean)²)
intercept = y_mean - slope × x_mean
forecast = slope × (n+1) + intercept
```

Where x is the month index and y is the revenue. The confidence interval is calculated from the residuals (differences between actual values and the trend line). This gives a forecast range rather than a single number, which is more honest and more useful.

**Period Comparison:**
Calculates week-over-week and month-over-month change as a percentage. Uses MySQL `YEARWEEK()` and `MONTH()` functions to isolate the current and previous periods.

---

### rag_engine.py — Retrieval Augmented Generation

RAG improves SQL generation accuracy by providing the LLM with examples of questions that have been answered correctly before.

**How it works:**

1. Every successful query is saved: question text + SQL that worked
2. Keywords are extracted from the question (stop words removed)
3. Keywords are stored in MySQL as a JSON array
4. When a new question arrives, keywords are extracted
5. Overlap between new keywords and stored keywords is calculated
6. Top 3 most similar past queries are retrieved
7. These are injected into the LLM prompt as few-shot examples

**Why this matters — few-shot learning:**

When the LLM sees examples of correct SQL for similar questions, it produces much more accurate SQL for the new question. It learns the column naming conventions, the table structure patterns, and the query style that works for this specific database.

**The similarity algorithm:**

```python
q_keywords = set(['revenue', 'channel', 'month'])
ex_keywords = set(['revenue', 'region', 'month'])
overlap = len(q_keywords & ex_keywords)  # = 2
```

Higher overlap = more similar question = higher priority in results.

**Self-improving system:**

The system gets better over time. After 100 questions, it has 100 examples. After 1000 questions, it has a rich library of patterns. New questions benefit from all previous successful queries.

---

### auto_indexer.py — Zero Manual Database Tuning

Database indexes are critical for performance. A query that takes 30 seconds on an unindexed 10 million row table takes 0.1 seconds with the right index. But creating the right indexes requires knowing which columns are used in WHERE and GROUP BY clauses.

**How it decides which columns need indexes:**

The auto-indexer analyzes column names against known patterns:

```
DATE columns     → 'date', 'time', 'created', 'timestamp'
CATEGORY columns → 'channel', 'type', 'status', 'region'
ID/KEY columns   → 'id', 'index', 'code', 'key', 'number'
AMOUNT columns   → 'total', 'amount', 'price', 'revenue'
```

If a column name matches a pattern AND the table has more than 1000 rows, an index is created automatically.

**The TEXT column problem:**

MySQL cannot create a standard index on a TEXT column without specifying a prefix length. The auto-indexer handles this by checking the column's actual data type and using a 50-character prefix for TEXT columns:

```sql
CREATE INDEX idx_sales_order_channel 
ON sales_order (channel(50))
```

**When it runs:**
- On application startup (indexes all existing tables)
- After every CSV upload (indexes the new table immediately)
- After every Google Sheets sync (indexes new data)

---

### memory.py — Conversation Persistence

Stores every message in MySQL so conversation context survives browser refreshes, logouts, and device changes.

**How context is maintained:**

The last 6 messages (3 exchanges) are retrieved and formatted into the LLM prompt:

```
User: What is total revenue?
Bot: Total revenue is $2.47B

User: Break it down by channel
```

The LLM sees the previous exchange and understands that "break it down" refers to revenue, not a new topic. This enables natural multi-turn conversation.

**Why MySQL instead of sessions:**

Flask sessions use browser cookies. They disappear when the browser closes. Storing memory in MySQL means the conversation persists forever and is accessible from any device. It also allows admins to see all conversations in the audit panel.

---

### local_engine.py — Query Cache

The query cache stores the results of successful queries so identical questions never hit the LLM again.

**Cache key:**
A hash of the normalized question text (lowercased, stripped of extra spaces).

**Cache behavior:**
- Hit rate check: if the question was asked before within the TTL (1 hour), return the cached result instantly
- Hit counter: tracks how many times each cached result is served
- TTL expiry: cache entries expire after 1 hour to ensure data freshness

**Impact on API costs:**
In a company where 50 users ask similar questions, the same "total revenue" query might be asked 20 times per day. With the cache, only the first instance hits the LLM. The other 19 are served from MySQL in milliseconds at zero cost.

---

### optimizer.py — Query Performance

Wraps SQL execution with timeout protection and pagination.

**Timeout protection:**

Runs the SQL query in a separate Python thread. If the query exceeds 10 seconds, the thread is abandoned and the user receives a helpful error message rather than waiting indefinitely. This prevents runaway queries from blocking the entire application.

**MySQL execution time limit:**

Also sets MySQL's own `MAX_EXECUTION_TIME` session variable before each query. This provides a second layer of protection at the database level.

**Pagination:**

For large result sets, the executor can return results in pages of 100 rows. This prevents the browser from freezing when a query returns thousands of rows. The UI shows a "Load More" button when more results are available.

---

### proactive_analyst.py — Autonomous Analysis

This module makes the system behave like a real data analyst who proactively monitors the business and reports findings without being asked.

**Daily briefing at 9am:**

The APScheduler triggers this module every morning. It runs the full analytics pipeline, identifies the most important findings, and stores a formatted HTML report in MySQL. When users open the app, they see a notification that their briefing is ready.

**The briefing contains:**
- Revenue overview with day-over-day comparison
- Order volume and average order value
- Top performing products and channels
- Any anomalies detected by the z-score algorithm
- Next month revenue forecast

**Proactive greeting:**

When a user opens the chat interface, the system checks for anomalies in real-time. If anything unusual is found, the bot speaks first before the user says anything:

*"Before you ask — I noticed revenue dropped 23% yesterday. Want me to investigate what caused this?"*

This is the behavior of a real analyst who has already done their morning review.

---

### alert_engine.py — In-App KPI Monitoring

Users define rules. The system watches the numbers and creates in-app notifications when rules are triggered.

**Example rules:**
- Revenue today drops below $50,000
- Orders in last hour equals 0
- Average order value drops below $100

**How it checks:**

APScheduler runs `check_all_alerts()` every hour. For each active rule, it gets the current metric value from analytics_engine.py and evaluates the condition. If the condition is true, it creates a notification in the `notifications` MySQL table.

**In-app notification bell:**

The chat interface polls `/api/notifications` every 2 minutes. When new notifications exist, a red badge appears on the bell icon in the header. Clicking the bell shows all unread notifications in a dropdown panel.

**No email — intentional design decision:**

Email is asynchronous, passive, and disconnected from the analytical workflow. A real data analyst does not send you an email when they notice something. They tell you directly when you are looking at the data. The in-app notification system keeps alerts in the context where they are most actionable.

---

### sync_manager.py + sheets_connector.py — Live Data

**Google Sheets Sync:**

Companies often maintain live data in Google Sheets — daily sales trackers, budget spreadsheets, inventory sheets. This connector checks registered sheets every 5 minutes and syncs any changes to MySQL automatically.

**Technical flow:**
1. APScheduler triggers `sync_all_due()` every 5 minutes
2. Queries `_sync_sources` table for sources due for sync
3. For each due source, calls Google Sheets API via `gspread`
4. Downloads all rows as a list of dictionaries
5. Converts to Pandas DataFrame
6. Cleans column names (lowercase, replace spaces with underscores)
7. Writes to MySQL using SQLAlchemy `to_sql(if_exists='replace')`
8. Runs auto-indexer on the updated table
9. Clears the query cache so stale results are not served

**Webhook endpoint:**

External systems (Shopify, Salesforce, SAP, custom ERP) can push data directly to `/webhook/receive` via HTTP POST. Token-based authentication prevents unauthorized data injection. Each webhook event is logged with IP address and row count.

---

### report_engine.py — Automated Report Generation

Generates complete business reports as HTML documents. Users trigger reports by typing "generate weekly report" in the chat or clicking report buttons in the dashboard.

**What a weekly report contains:**
- KPI summary (revenue, orders, average order value)
- Revenue by channel table with percentage breakdown
- Top 10 products ranked by revenue
- Bottom 5 products (for attention)
- Week-over-week comparison
- Next month forecast

Reports are saved to the `report_history` table and can be accessed anytime. The HTML format means they can be printed, shared as links, or converted to PDF using the browser's print function.

---

## Library Explanations

### Flask

Flask is a micro web framework for Python. It handles HTTP routing, request/response cycles, templating, and session management. Unlike Django, Flask has no built-in ORM or admin panel — everything is explicitly added. This makes it lighter and more transparent for a project where we want full control over every component.

Key Flask concepts used:
- `@app.route()` decorators map URL paths to Python functions
- `request.get_json()` parses incoming JSON from the browser
- `jsonify()` converts Python dictionaries to JSON responses
- `render_template()` renders Jinja2 HTML templates

### Flask-Login

Manages user sessions. After a user logs in, Flask-Login stores their user ID in a signed session cookie. On every subsequent request, `@login_required` checks this cookie and either allows the request or redirects to the login page.

The `current_user` proxy object is available in every route and template, providing the logged-in user's ID, username, and role without additional database queries.

### Flask-Bcrypt

Bcrypt is a password hashing algorithm designed to be deliberately slow. This is a feature, not a bug. If an attacker steals the database, they cannot reverse-engineer passwords because bcrypt makes brute-force attacks computationally expensive.

Each password is hashed with a random salt so identical passwords produce different hashes. The salt is stored inside the hash string itself.

### SQLAlchemy

SQLAlchemy is used specifically for dynamic table creation when loading CSV files. Its `DataFrame.to_sql()` method automatically:
- Infers column types from Pandas dtypes
- Creates the table if it does not exist
- Handles MySQL-specific type conversions
- Manages connection pooling

Raw MySQL connector is used for all other queries because it provides more control and transparency for security-critical operations.

### Pandas

Used exclusively for data ingestion. When a CSV or Excel file is uploaded:
- `pd.read_csv()` or `pd.read_excel()` loads the file
- Auto-detects the delimiter (comma, semicolon, tab)
- `df.columns` manipulation cleans column names to MySQL-compatible format
- `dropna(how='all')` removes completely empty rows
- Data type inference prepares columns for MySQL storage

Pandas is not used for analytics calculations — those are done in pure Python and MySQL to keep dependencies minimal and calculations transparent.

### Groq API

Groq provides a cloud API for running large language models. The key advantage over OpenAI is speed — Groq uses custom hardware (Language Processing Units) that runs inference significantly faster. A 70B parameter model responds in under 1 second.

The API is called using the official `groq` Python library. Requests include a system message (persona and instructions) and a user message (the actual prompt). Temperature is set to 0 for deterministic, consistent SQL generation.

### APScheduler

BackgroundScheduler runs Python functions on a schedule in a background thread, separate from the Flask request-handling threads. This allows the application to run scheduled tasks without blocking user requests.

Jobs configured:
- Every 5 minutes: Google Sheets sync
- Every 30 minutes: CSV file folder check
- Every 60 minutes: KPI alert rule evaluation
- Daily at 9:00 AM: Daily briefing generation

`atexit.register(scheduler.shutdown)` ensures the scheduler stops cleanly when the application exits.

### gspread + google-auth

`gspread` is a Python client for the Google Sheets API. It authenticates using a service account JSON credentials file, opens spreadsheets by URL, and downloads all rows as a list of dictionaries.

`google-auth` handles the OAuth2 authentication flow using service account credentials, generating and refreshing access tokens automatically.

### Chart.js

A JavaScript library that renders interactive charts on HTML canvas elements. Used in the chat interface and dashboard. Charts are generated client-side from JSON data returned by the server — no chart images are generated on the server.

Three chart types are used:
- **Bar chart**: categorical comparisons (revenue by product, orders by warehouse)
- **Line chart**: time-series trends (daily revenue over 30 days)
- **Pie chart**: proportional breakdowns (revenue by channel)

The chart type is selected automatically based on keywords in the question. Questions containing "trend", "monthly", "over time" get line charts. Questions containing "breakdown", "distribution", "percentage" get pie charts. All others get bar charts.

---

## Security Architecture

The system implements defense in depth — multiple independent security layers so that a failure in one layer does not compromise the entire system.

```
Layer 1: Authentication (Flask-Login + bcrypt)
         No unauthenticated access to any route
         Passwords hashed with bcrypt (cost factor 12)

Layer 2: Authorization (RBAC)
         Role checked on every request
         Schema filtered before LLM call
         Table permissions enforced at SQL level

Layer 3: Input Protection (data_shield.py)
         Real values never sent to LLM
         Schema anonymized before transmission
         Sensitive patterns auto-redacted

Layer 4: Query Validation (security.py)
         Every LLM-generated SQL validated
         Dangerous patterns blocked
         Forbidden tables protected

Layer 5: Audit Trail (AuditLogger)
         Every action logged
         Zero actual data in logs
         GDPR compliant metadata only

Layer 6: Local LLM Option (Ollama)
         Run entirely offline
         Zero data leaves network
         Complete air-gap capability
```

---

## Data Flow

**Complete request lifecycle for a data question:**

```
1. User types: "What is revenue by channel?"

2. Browser sends POST /chat with JSON body

3. Flask @login_required checks session cookie
   → Valid: continue
   → Invalid: redirect to /login

4. load_user() fetches user from MySQL
   → Gets role: admin/analyst/viewer

5. cache_get(question) checks MySQL cache
   → Hit: return cached result, 0 API calls
   → Miss: continue

6. get_history(user_id) fetches last 6 messages
   from conversations table

7. get_schema() builds table structure string
   → Only column names and types
   → No actual data values

8. filter_schema_for_user() removes tables
   the user's role cannot access

9. rag.find_similar(question) queries
   _query_examples table
   → Returns 3 most similar past queries
   → Injected as few-shot examples

10. data_shield.anonymize_schema(schema)
    → Replaces sample values with [TEXT], [NUMBER]
    (skipped if Ollama is running locally)

11. process_question_complete() calls LLM
    → Single prompt returns JSON
    → intent: DATA_QUESTION
    → sql: SELECT channel, SUM(line_total)...
    → followups: [3 suggestions]

12. validator.validate(sql) runs firewall
    → Checks for dangerous keywords
    → Checks forbidden table access
    → Adds LIMIT if missing
    → Returns (True, "Valid", clean_sql)

13. check_table_access(user, sql) verifies
    the user's role permits access to
    the tables referenced in the SQL

14. execute_sql(sql) runs the query
    → Wrapped in timeout thread (10 seconds)
    → Returns results as list of tuples

15. _format_simple_result() checks if result
    is a single value (e.g. total revenue)
    → Yes: format as "$2,471,937,798.00"
    → No: call explain_results() for LLM explanation

16. _build_chart() analyzes question keywords
    → "channel" + multiple rows → pie chart
    → Returns Chart.js configuration JSON

17. audit.log() writes to _audit_log
    → user_id, role, table name, row count, ms
    → Nothing about the actual data

18. cache_set() stores in _query_cache
    → TTL: 1 hour

19. save_message() writes to conversations
    → Both user question and bot answer

20. rag.save_example() stores Q+SQL pair
    → Future similar questions benefit

21. Response JSON sent to browser:
    {
      "answer": "Revenue by channel: Wholesale $1.3B...",
      "sql": "SELECT channel, SUM(line_total)...",
      "row_count": 3,
      "chart": { type: "pie", data: {...} },
      "followups": ["...", "...", "..."],
      "protected": true,
      "elapsed": 0.312
    }

22. Browser renders answer, draws Chart.js chart,
    shows follow-up suggestion chips
```

---

## Role Based Access Control

Three built-in roles with different capabilities:

**Admin:**
- Access to all tables
- Access to admin panel
- Can create and manage users
- Can create custom roles
- Can view audit logs and security reports
- Can configure KPI alerts
- Can manage data sync sources

**Analyst:**
- Access to all business data tables
- Can upload new CSV and Excel files
- Cannot access admin panel
- Cannot see other users' data or settings

**Viewer:**
- Access only to tables explicitly assigned by admin
- Read-only query access
- Cannot upload files
- Cannot access admin panel
- Schema is filtered to show only permitted tables

**How RBAC is enforced at two levels:**

1. **Schema level:** `filter_schema_for_user()` removes unauthorized tables from the schema string before it reaches the LLM. This means the LLM cannot even generate SQL referencing those tables.

2. **SQL level:** `check_table_access()` parses the generated SQL, extracts all table names from FROM and JOIN clauses, and verifies each against the user's allowed tables. Even if the LLM somehow generated SQL for a forbidden table, this check catches it.

---

## Performance Optimization

**Database indexes:**

Without an index, MySQL performs a full table scan — it reads every row to find matches. On a 10 million row table this takes 30+ seconds. With an index, MySQL uses a B-tree data structure to jump directly to matching rows. The same query takes 0.1 seconds.

The auto-indexer creates indexes based on column name patterns because these columns appear in WHERE and GROUP BY clauses most frequently:
- Date columns: used in date range filters
- Category columns: used in GROUP BY aggregations
- ID/key columns: used in JOIN conditions
- Amount columns: used in SUM and AVG aggregations

**Query cache:**

The cache stores question → (SQL + answer + row count + followups) pairs. The cache key is an MD5 hash of the normalized question. When the same question is asked again within one hour, the cached result is returned without any LLM or SQL calls. Response time drops from 2 seconds to 10 milliseconds.

**Connection management:**

Each database query opens a connection, executes, and closes. MySQL's connection pool (managed by the mysql-connector-python driver) reuses connections from a pool rather than creating new TCP connections for each query. This reduces connection overhead from ~50ms to ~1ms per query.

---

## Local LLM Architecture

**Why local LLM matters:**

Even with schema anonymization, sending queries to a cloud API means trusting a third party with your business questions. The patterns of questions alone can reveal sensitive business intelligence. A local LLM eliminates this entirely.

**Ollama:**

Ollama is an open-source application that runs language models locally on consumer hardware. It exposes a REST API on `localhost:11434` that is compatible with the same interface used for cloud LLMs. The application code detects whether Ollama is running and uses it preferentially over cloud APIs.

**The decision logic:**

```python
if is_ollama_running():
    # Full schema sent locally — zero exposure
    use_full_schema = True
    endpoint = "http://localhost:11434/api/chat"
else:
    # Schema anonymized before cloud transmission
    use_full_schema = False
    endpoint = "https://api.groq.com/..."
```

**Performance reality:**

LLaMA 3.1 8B running on CPU takes 20-60 seconds per query depending on hardware. On a consumer GPU (RTX 3080 or better), this drops to 1-3 seconds. The local LLM is installed and available for organizations with appropriate hardware. For development and demonstration, Groq cloud is used as the primary endpoint.

---

## Setup & Installation

### Prerequisites

```
Python 3.11 or higher
MySQL 8.0 or higher
Git
```

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/text-to-sql-chatbot
cd text-to-sql-chatbot

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
```

### Configure `.env`

```env
GROQ_API_KEY=your_groq_api_key_from_console.groq.com
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=chatbot_db
SECRET_KEY=any_random_string_at_least_32_characters
GOOGLE_CREDENTIALS_PATH=credentials/google_sheets.json
```

### Database Setup

```bash
# In MySQL Workbench or MySQL CLI:
mysql -u root -p < docker/mysql/init.sql
```

### Load Sample Data

```bash
# Place CSV files in the data/ folder
# The file watcher loads them automatically on startup
python app.py
```

### Access the Application

```
http://localhost:5000
```

Register the first account — it automatically becomes admin.

### Optional: Local LLM Setup

```bash
# Install Ollama from https://ollama.com/download
# Then pull the model:
ollama pull llama3.1

# Start the Ollama server:
ollama serve

# The application automatically detects and uses it
```

---

## Docker Deployment

Docker packages the entire application and its dependencies into containers. The `docker-compose.yml` file defines two services: `db` (MySQL) and `app` (Flask). A single command starts both.

```bash
# Build and start
docker-compose up --build

# Run in background
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop everything
docker-compose down

# Stop and delete all data
docker-compose down -v
```

**What happens on first start:**
1. Docker pulls `mysql:8.0` and `python:3.11-slim` images
2. MySQL container starts and runs `init.sql` automatically
3. All tables are created with correct schema
4. Python container installs requirements
5. Flask app starts on port 5000
6. Auto-indexer runs on all tables
7. Scheduler starts background jobs

**Important:** Set `DB_HOST=db` in `.env` when using Docker. Inside Docker's network, services communicate by service name, not `localhost`.

---

## Tech Stack Summary

| Category | Technology | Purpose |
|---|---|---|
| Language | Python 3.11 | Primary backend language |
| Web Framework | Flask 3.1 | HTTP routing and request handling |
| Authentication | Flask-Login | Session management |
| Password Security | Flask-Bcrypt | Bcrypt password hashing |
| Primary LLM | LLaMA 3.3 70B via Groq | Natural language to SQL |
| Local LLM | LLaMA 3.1 via Ollama | Zero-exposure local inference |
| Database | MySQL 8.0 | Primary data storage |
| ORM | SQLAlchemy | Dynamic table creation |
| Data Processing | Pandas | CSV and Excel ingestion |
| Scheduling | APScheduler | Background jobs |
| Sheets Integration | gspread + google-auth | Google Sheets sync |
| Frontend Charts | Chart.js | Data visualization |
| Containerization | Docker + Docker Compose | Deployment |
| Anomaly Detection | Custom z-score (Python) | Statistical outlier detection |
| Forecasting | Custom linear regression | Revenue prediction |
| RAG | Custom keyword similarity | Few-shot SQL improvement |
| Security | Custom SQL firewall | Query validation |
| Compliance | Custom audit logger | Zero-knowledge GDPR logging |

---

## Key Engineering Decisions

**1. No LangChain**

LangChain adds abstraction layers that obscure what is actually happening. Every LLM interaction in this system is explicit Python code. This makes debugging easier, performance more predictable, and the security model transparent.

**2. No Vector Database**

ChromaDB, Pinecone, and similar vector databases add significant complexity and infrastructure cost. The RAG system uses keyword overlap scoring stored in MySQL. For a SQL generation task with structured queries, this approach performs comparably to vector similarity at a fraction of the complexity.

**3. Single Prompt Strategy**

Combining intent detection, SQL generation, explanation, and follow-up generation into one LLM call reduces API costs by 75% and cuts latency in half. The structured JSON output format makes parsing reliable.

**4. Pure Python Analytics**

The anomaly detection and forecasting modules use no ML libraries. Z-score and linear regression are implemented in 20 lines of Python each. This makes the analytics transparent, auditable, and dependency-free. A junior engineer can read and verify the math directly.

**5. Schema-Only LLM Interface**

The LLM never sees actual data values. It only sees column names and types. This is the most important architectural decision for enterprise adoption. No matter what the LLM provider does with the prompt, they cannot expose actual business data because they never received it.

---

*Built as a portfolio project demonstrating NLP, SQL generation, LLM integration, enterprise security patterns, and full-stack Python engineering.*