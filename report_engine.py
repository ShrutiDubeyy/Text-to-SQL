from datetime import datetime, timedelta
from analytics_engine import analytics
from db import get_connection


class ReportEngine:
    """
    Generates comprehensive business reports.
    User says "weekly report" → full HTML report.
    """

    def generate_report(self, report_type='weekly',
                         user_id=None):
        """
        Generate full business report.
        report_type: daily, weekly, monthly
        """
        print(f"[Report] Generating {report_type} report")

        data = analytics.get_dashboard_data()

        if report_type == 'weekly':
            html = self._weekly_report(data)
        elif report_type == 'monthly':
            html = self._monthly_report(data)
        else:
            html = self._daily_report(data)

        self._save_report(user_id, report_type, html)
        return html

    def _daily_report(self, data):
        return self._build_report_html(
            'Daily Sales Report',
            datetime.now().strftime('%B %d, %Y'),
            data
        )

    def _weekly_report(self, data):
        end   = datetime.now()
        start = end - timedelta(days=7)
        period = (
            f"{start.strftime('%b %d')} — "
            f"{end.strftime('%b %d, %Y')}"
        )
        return self._build_report_html(
            'Weekly Sales Report',
            period, data
        )

    def _monthly_report(self, data):
        return self._build_report_html(
            'Monthly Sales Report',
            datetime.now().strftime('%B %Y'),
            data
        )

    def _build_report_html(self, title,
                            period, data):
        kpis     = data['kpis']
        channels = data['by_channel']
        products = data['top_products']
        trend    = data['daily_trend']
        forecast = data['forecast']

        # Channel table rows
        channel_rows = ''
        for c in channels:
            channel_rows += f"""
            <tr>
              <td>{c['channel']}</td>
              <td>${float(c['revenue']):,.2f}</td>
              <td>{c['orders']}</td>
              <td>${float(c['revenue'])/max(c['orders'],1):,.2f}</td>
            </tr>"""

        # Product table rows
        product_rows = ''
        for i, p in enumerate(products):
            product_rows += f"""
            <tr>
              <td>{i+1}</td>
              <td>{p['product']}</td>
              <td>${float(p['revenue']):,.2f}</td>
              <td>{p['orders']}</td>
            </tr>"""

        # Forecast section
        forecast_html = ''
        if forecast:
            forecast_html = f"""
            <div style="background:#eff6ff;
                        padding:20px;
                        border-radius:8px;
                        margin:24px 0;">
              <h2 style="color:#1e40af;">
                📈 Forecast
              </h2>
              <p>Next period projected revenue:
                <strong>
                  ${forecast['forecast']:,.0f}
                </strong>
                (range:
                ${forecast['low']:,.0f} —
                ${forecast['high']:,.0f})
              </p>
              <p>Trend direction:
                <strong>{forecast['trend'].upper()}</strong>
              </p>
            </div>"""

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
          <title>{title}</title>
          <style>
            body {{
              font-family:sans-serif;
              max-width:800px;
              margin:0 auto;
              padding:32px;
              color:#1e293b;
            }}
            h1 {{ color:#1e293b; }}
            h2 {{ color:#334155;font-size:18px; }}
            table {{
              width:100%;
              border-collapse:collapse;
              margin:12px 0;
            }}
            th {{
              background:#1e293b;
              color:white;
              padding:10px 12px;
              text-align:left;
              font-size:13px;
            }}
            td {{
              padding:10px 12px;
              border-bottom:1px solid #e2e8f0;
              font-size:13px;
            }}
            tr:hover td {{ background:#f8fafc; }}
            .kpi-grid {{
              display:grid;
              grid-template-columns:repeat(3,1fr);
              gap:16px;
              margin:24px 0;
            }}
            .kpi-card {{
              background:#f8fafc;
              padding:20px;
              border-radius:8px;
              text-align:center;
            }}
            .kpi-value {{
              font-size:28px;
              font-weight:700;
              color:#1e293b;
            }}
            .kpi-label {{
              font-size:12px;
              color:#64748b;
              margin-top:4px;
            }}
          </style>
        </head>
        <body>
          <h1>{title}</h1>
          <p style="color:#64748b">{period}</p>
          <hr style="border:none;
                     border-top:1px solid #e2e8f0;
                     margin:20px 0"/>

          <div class="kpi-grid">
            <div class="kpi-card">
              <div class="kpi-value">
                ${kpis['revenue_this_week']:,.0f}
              </div>
              <div class="kpi-label">
                Total Revenue
              </div>
            </div>
            <div class="kpi-card">
              <div class="kpi-value">
                {kpis['orders_today']:,}
              </div>
              <div class="kpi-label">
                Total Orders
              </div>
            </div>
            <div class="kpi-card">
              <div class="kpi-value">
                ${kpis['avg_order_value']:,.0f}
              </div>
              <div class="kpi-label">
                Avg Order Value
              </div>
            </div>
          </div>

          <h2>Revenue by Channel</h2>
          <table>
            <thead>
              <tr>
                <th>Channel</th>
                <th>Revenue</th>
                <th>Orders</th>
                <th>Avg Order</th>
              </tr>
            </thead>
            <tbody>{channel_rows}</tbody>
          </table>

          <h2>Top Products</h2>
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Product</th>
                <th>Revenue</th>
                <th>Orders</th>
              </tr>
            </thead>
            <tbody>{product_rows}</tbody>
          </table>

          {forecast_html}

          <p style="color:#94a3b8;font-size:11px;
                     text-align:center;
                     margin-top:32px;">
            Generated by AI Data Analyst Bot •
            {datetime.now().strftime('%Y-%m-%d %H:%M')}
          </p>
        </body>
        </html>"""

    def _save_report(self, user_id,
                     report_type, html):
        """Save report to database"""
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO report_history
                (user_id, report_type, report_html)
                VALUES (%s, %s, %s)
            """, (user_id, report_type, html))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[Report] Save error: {e}")

    def get_report_history(self, user_id=None,
                           limit=10):
        """Get recent reports"""
        try:
            conn   = get_connection()
            cursor = conn.cursor(dictionary=True)
            if user_id:
                cursor.execute("""
                    SELECT id, user_id, report_type,
                           created_at
                    FROM report_history
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (user_id, limit))
            else:
                cursor.execute("""
                    SELECT id, user_id, report_type,
                           created_at
                    FROM report_history
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
            reports = cursor.fetchall()
            cursor.close()
            conn.close()
            for r in reports:
                if r.get('created_at'):
                    r['created_at'] = \
                        r['created_at'].strftime(
                            '%Y-%m-%d %H:%M:%S')
            return reports
        except Exception as e:
            print(f"[Report] History error: {e}")
            return []


report_engine = ReportEngine()