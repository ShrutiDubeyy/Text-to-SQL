from datetime import datetime, timedelta
from analytics_engine import analytics
from db import get_connection
import os


class ProactiveAnalyst:
    """
    Generates daily briefings automatically.
    Runs at 9am every day.
    Finds insights without being asked.
    """

    def generate_daily_briefing(self):
        """
        Generate complete daily business briefing.
        Pure Python — no LLM for data analysis.
        LLM only used for narrative writing.
        """
        print("[Analyst] 📊 Generating daily briefing...")

        data = analytics.get_dashboard_data()

        # Build briefing sections
        sections = []

        # 1. Revenue section
        kpis       = data['kpis']
        rev_today  = kpis['revenue_today']
        rev_yest   = kpis['revenue_yesterday']
        rev_change = kpis['revenue_change']

        direction = "📈" if rev_change > 0 else "📉"

        sections.append({
            'title': 'Revenue Overview',
            'content': (
                f"Today: ${rev_today:,.2f} "
                f"({direction} {abs(rev_change):.1f}% "
                f"vs yesterday)\n"
                f"Yesterday: ${rev_yest:,.2f}\n"
                f"This week: "
                f"${kpis['revenue_this_week']:,.2f}\n"
                f"This month: "
                f"${kpis['revenue_this_month']:,.2f}"
            )
        })

        # 2. Orders section
        ord_today  = kpis['orders_today']
        ord_yest   = kpis['orders_yesterday']
        ord_change = kpis['orders_change']
        ord_dir    = "📈" if ord_change > 0 else "📉"

        sections.append({
            'title': 'Orders',
            'content': (
                f"Today: {ord_today:,} orders "
                f"({ord_dir} "
                f"{abs(ord_change):.1f}% vs yesterday)\n"
                f"Avg order value: "
                f"${kpis['avg_order_value']:,.2f}"
            )
        })

        # 3. Top performers
        top = data['top_products'][:3]
        if top:
            top_str = '\n'.join([
                f"{i+1}. {p['product']} — "
                f"${float(p['revenue']):,.0f}"
                for i, p in enumerate(top)
            ])
            sections.append({
                'title': 'Top Products Today',
                'content': top_str
            })

        # 4. Channel performance
        channels = data['by_channel']
        if channels:
            best  = channels[0]
            worst = channels[-1]
            sections.append({
                'title': 'Channel Performance',
                'content': (
                    f"Best:  {best['channel']} "
                    f"(${float(best['revenue']):,.0f})\n"
                    f"Worst: {worst['channel']} "
                    f"(${float(worst['revenue']):,.0f})"
                )
            })

        # 5. Anomalies detected
        anomalies = data['anomalies']
        if anomalies:
            anom_str = '\n'.join([
                f"⚠️ {a['message']}"
                for a in anomalies[:3]
            ])
            sections.append({
                'title': 'Anomalies Detected',
                'content': anom_str
            })
        else:
            sections.append({
                'title': 'Anomalies',
                'content': '✅ No anomalies detected today'
            })

        # 6. Forecast
        forecast = data['forecast']
        if forecast:
            sections.append({
                'title': 'Next Month Forecast',
                'content': (
                    f"Projected: "
                    f"${forecast['forecast']:,.0f}\n"
                    f"Range: ${forecast['low']:,.0f}"
                    f" — ${forecast['high']:,.0f}\n"
                    f"Trend: {forecast['trend'].upper()}"
                )
            })

        # Build HTML report
        html = self._build_briefing_html(
            sections, data)

        # Save to database
        self._save_briefing(html, sections)

        print("[Analyst] ✅ Daily briefing generated")
        return {
            'sections': sections,
            'html':     html,
            'data':     data
        }

    def _build_briefing_html(self, sections, data):
        """Build beautiful HTML briefing"""
        date_str = datetime.now().strftime(
            '%A, %B %d, %Y')

        kpis = data['kpis']

        sections_html = ''
        for s in sections:
            content_html = s['content'].replace(
                '\n', '<br>')
            sections_html += f"""
            <div style="margin-bottom:20px;
                        padding:16px;
                        background:#f8fafc;
                        border-radius:8px;
                        border-left:3px solid #3b82f6;">
              <h3 style="margin:0 0 8px;
                          color:#1e40af;
                          font-size:14px;">
                {s['title']}
              </h3>
              <p style="margin:0;color:#374151;
                         font-size:13px;
                         line-height:1.6;">
                {content_html}
              </p>
            </div>"""

        return f"""
        <div style="font-family:sans-serif;
                    max-width:680px;
                    margin:0 auto;
                    padding:24px;">
          <div style="background:#1e293b;
                      color:white;
                      padding:24px;
                      border-radius:12px;
                      margin-bottom:24px;">
            <h1 style="margin:0 0 4px;font-size:22px;">
              📊 Daily Business Briefing
            </h1>
            <p style="margin:0;opacity:0.7;
                       font-size:14px;">
              {date_str}
            </p>
          </div>

          <div style="display:grid;
                      grid-template-columns:1fr 1fr 1fr;
                      gap:12px;margin-bottom:24px;">
            <div style="background:#eff6ff;
                        padding:16px;border-radius:8px;
                        text-align:center;">
              <div style="font-size:22px;
                           font-weight:700;
                           color:#1d4ed8;">
                ${kpis['revenue_today']:,.0f}
              </div>
              <div style="font-size:12px;
                           color:#64748b;">
                Revenue today
              </div>
            </div>
            <div style="background:#f0fdf4;
                        padding:16px;border-radius:8px;
                        text-align:center;">
              <div style="font-size:22px;
                           font-weight:700;
                           color:#16a34a;">
                {kpis['orders_today']:,}
              </div>
              <div style="font-size:12px;
                           color:#64748b;">
                Orders today
              </div>
            </div>
            <div style="background:#fefce8;
                        padding:16px;border-radius:8px;
                        text-align:center;">
              <div style="font-size:22px;
                           font-weight:700;
                           color:#ca8a04;">
                ${kpis['avg_order_value']:,.0f}
              </div>
              <div style="font-size:12px;
                           color:#64748b;">
                Avg order value
              </div>
            </div>
          </div>

          {sections_html}

          <p style="color:#94a3b8;font-size:11px;
                     text-align:center;
                     margin-top:24px;">
            Generated by AI Data Analyst Bot •
            {datetime.now().strftime('%H:%M')}
          </p>
        </div>"""

    def _save_briefing(self, html, sections):
        """Save briefing to database"""
        try:
            summary = ' | '.join([
                f"{s['title']}: "
                f"{s['content'][:50]}"
                for s in sections[:3]
            ])
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO daily_briefings
                (briefing_date, summary, full_report)
                VALUES (CURDATE(), %s, %s)
                ON DUPLICATE KEY UPDATE
                    summary      = VALUES(summary),
                    full_report  = VALUES(full_report)
            """, (summary, html))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[Analyst] Save error: {e}")

    def get_latest_briefing(self):
        """Get most recent briefing"""
        try:
            conn   = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM daily_briefings
                ORDER BY briefing_date DESC
                LIMIT 1
            """)
            briefing = cursor.fetchone()
            cursor.close()
            conn.close()
            if briefing and briefing.get(
                    'briefing_date'):
                briefing['briefing_date'] = \
                    str(briefing['briefing_date'])
            return briefing
        except Exception as e:
            print(f"[Analyst] Fetch error: {e}")
            return None


proactive_analyst = ProactiveAnalyst()