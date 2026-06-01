import statistics
from datetime import datetime, timedelta
from db import get_connection


class AnalyticsEngine:
    """
    Pure Python analytics — no LLM needed.
    Runs real data analyst calculations.
    """

    def __init__(self, table='sales_order'):
        self.table      = table
        self.date_col   = 'orderdate'
        self.amount_col = 'line_total'
        self.product_col = 'product_description_index'
        self.channel_col = 'channel'
        self.customer_col = 'customer_name_index'

    def _query(self, sql, params=None):
        """Run SQL and return results"""
        try:
            conn   = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, params or ())
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            return rows
        except Exception as e:
            print(f"[Analytics] Query error: {e}")
            return []

    # ── METRIC 1: Revenue Today ──────────────────────

    def get_revenue_today(self):
        rows = self._query(f"""
            SELECT COALESCE(SUM({self.amount_col}), 0)
                   as revenue
            FROM {self.table}
            WHERE DATE({self.date_col}) = CURDATE()
        """)
        return float(rows[0]['revenue']) if rows else 0

    def get_revenue_yesterday(self):
        rows = self._query(f"""
            SELECT COALESCE(SUM({self.amount_col}), 0)
                   as revenue
            FROM {self.table}
            WHERE DATE({self.date_col}) =
                  CURDATE() - INTERVAL 1 DAY
        """)
        return float(rows[0]['revenue']) if rows else 0

    def get_revenue_this_week(self):
        rows = self._query(f"""
            SELECT COALESCE(SUM({self.amount_col}), 0)
                   as revenue
            FROM {self.table}
            WHERE YEARWEEK({self.date_col}) =
                  YEARWEEK(CURDATE())
        """)
        return float(rows[0]['revenue']) if rows else 0

    def get_revenue_last_week(self):
        rows = self._query(f"""
            SELECT COALESCE(SUM({self.amount_col}), 0)
                   as revenue
            FROM {self.table}
            WHERE YEARWEEK({self.date_col}) =
                  YEARWEEK(CURDATE()) - 1
        """)
        return float(rows[0]['revenue']) if rows else 0

    def get_revenue_this_month(self):
        rows = self._query(f"""
            SELECT COALESCE(SUM({self.amount_col}), 0)
                   as revenue
            FROM {self.table}
            WHERE MONTH({self.date_col}) = MONTH(CURDATE())
            AND   YEAR({self.date_col})  = YEAR(CURDATE())
        """)
        return float(rows[0]['revenue']) if rows else 0

    # ── METRIC 2: Orders ─────────────────────────────

    def get_orders_today(self):
        rows = self._query(f"""
            SELECT COUNT(*) as orders
            FROM {self.table}
            WHERE DATE({self.date_col}) = CURDATE()
        """)
        return int(rows[0]['orders']) if rows else 0

    def get_orders_yesterday(self):
        rows = self._query(f"""
            SELECT COUNT(*) as orders
            FROM {self.table}
            WHERE DATE({self.date_col}) =
                  CURDATE() - INTERVAL 1 DAY
        """)
        return int(rows[0]['orders']) if rows else 0

    def get_avg_order_value(self):
        rows = self._query(f"""
            SELECT COALESCE(AVG({self.amount_col}), 0)
                   as avg_value
            FROM {self.table}
            WHERE DATE({self.date_col}) >= 
                  CURDATE() - INTERVAL 30 DAY
        """)
        return float(rows[0]['avg_value']) if rows else 0

    # ── METRIC 3: Channel Performance ────────────────

    def get_revenue_by_channel(self, days=30):
        return self._query(f"""
            SELECT {self.channel_col} as channel,
                   SUM({self.amount_col}) as revenue,
                   COUNT(*) as orders
            FROM {self.table}
            WHERE DATE({self.date_col}) >=
                  CURDATE() - INTERVAL {days} DAY
            GROUP BY {self.channel_col}
            ORDER BY revenue DESC
        """)

    # ── METRIC 4: Top Products ────────────────────────

    def get_top_products(self, limit=5, days=30):
        return self._query(f"""
            SELECT {self.product_col} as product,
                   SUM({self.amount_col}) as revenue,
                   COUNT(*) as orders
            FROM {self.table}
            WHERE DATE({self.date_col}) >=
                  CURDATE() - INTERVAL {days} DAY
            GROUP BY {self.product_col}
            ORDER BY revenue DESC
            LIMIT {limit}
        """)

    # ── METRIC 5: Daily Trend ─────────────────────────

    def get_daily_trend(self, days=30):
        return self._query(f"""
            SELECT DATE({self.date_col}) as date,
                   SUM({self.amount_col}) as revenue,
                   COUNT(*) as orders
            FROM {self.table}
            WHERE DATE({self.date_col}) >=
                  CURDATE() - INTERVAL {days} DAY
            GROUP BY DATE({self.date_col})
            ORDER BY date ASC
        """)

    # ── METRIC 6: Anomaly Detection ──────────────────

    def detect_anomalies(self):
        """
        Find unusual patterns using
        standard deviation.
        YOUR algorithm — no LLM.
        """
        anomalies = []

        # Get daily revenue for last 30 days
        daily = self.get_daily_trend(30)
        if len(daily) < 7:
            return anomalies

        revenues = [float(d['revenue'])
                    for d in daily]

        if not revenues:
            return anomalies

        mean   = statistics.mean(revenues)
        stdev  = statistics.stdev(revenues) \
                 if len(revenues) > 1 else 0

        if stdev == 0:
            return anomalies

        for day in daily:
            rev     = float(day['revenue'])
            z_score = (rev - mean) / stdev

            if abs(z_score) > 2:
                anomalies.append({
                    'date':    str(day['date']),
                    'revenue': rev,
                    'z_score': round(z_score, 2),
                    'type': 'spike'
                             if z_score > 0
                             else 'drop',
                    'message': (
                        f"Revenue on {day['date']} "
                        f"was {'above' if z_score > 0 else 'below'} "
                        f"normal by "
                        f"{abs(z_score):.1f} std deviations"
                    )
                })

        return anomalies

    # ── METRIC 7: Period Comparison ───────────────────

    def compare_periods(self, period='week'):
        """
        Compare current period vs previous.
        Returns change percentage.
        """
        if period == 'week':
            current  = self.get_revenue_this_week()
            previous = self.get_revenue_last_week()
        elif period == 'month':
            current  = self.get_revenue_this_month()
            previous = self._get_last_month_revenue()
        else:
            current  = self.get_revenue_today()
            previous = self.get_revenue_yesterday()

        if previous == 0:
            return {
                'current':  current,
                'previous': previous,
                'change':   0,
                'direction': 'neutral'
            }

        change = ((current - previous) / previous) * 100

        return {
            'current':   round(current, 2),
            'previous':  round(previous, 2),
            'change':    round(change, 1),
            'direction': 'up' if change > 0
                         else 'down'
        }

    def _get_last_month_revenue(self):
        rows = self._query(f"""
            SELECT COALESCE(SUM({self.amount_col}), 0)
                   as revenue
            FROM {self.table}
            WHERE MONTH({self.date_col}) =
                  MONTH(CURDATE() - INTERVAL 1 MONTH)
            AND   YEAR({self.date_col}) =
                  YEAR(CURDATE() - INTERVAL 1 MONTH)
        """)
        return float(rows[0]['revenue']) if rows else 0

    # ── METRIC 8: Forecast ────────────────────────────

    def forecast_next_month(self):
        """
        Simple linear regression forecast.
        YOUR math — no LLM or ML library.
        """
        # Get last 6 months of revenue
        rows = self._query(f"""
            SELECT
                YEAR({self.date_col})  as year,
                MONTH({self.date_col}) as month,
                SUM({self.amount_col}) as revenue
            FROM {self.table}
            GROUP BY
                YEAR({self.date_col}),
                MONTH({self.date_col})
            ORDER BY year ASC, month ASC
            LIMIT 12
        """)

        if len(rows) < 3:
            return None

        values = [float(r['revenue']) for r in rows]
        n      = len(values)

        # Linear regression
        x_mean = (n - 1) / 2
        y_mean = statistics.mean(values)

        numerator   = sum(
            (i - x_mean) * (values[i] - y_mean)
            for i in range(n)
        )
        denominator = sum(
            (i - x_mean) ** 2 for i in range(n)
        )

        if denominator == 0:
            return None

        slope     = numerator / denominator
        intercept = y_mean - slope * x_mean

        # Forecast next period
        forecast = slope * n + intercept

        # Confidence range (±1 std dev)
        residuals = [
            values[i] - (slope * i + intercept)
            for i in range(n)
        ]
        std_dev = statistics.stdev(residuals) \
                  if len(residuals) > 1 else 0

        return {
            'forecast':   round(max(forecast, 0), 2),
            'low':        round(max(
                              forecast - std_dev, 0
                          ), 2),
            'high':       round(
                              forecast + std_dev, 2
                          ),
            'trend':      'up' if slope > 0 else 'down',
            'slope':      round(slope, 2),
            'confidence': round(
                (1 - std_dev / y_mean) * 100, 1
            ) if y_mean > 0 else 0
        }

    # ── FULL DASHBOARD DATA ───────────────────────────

    def get_dashboard_data(self):
        """
        Get ALL metrics for dashboard in one call.
        """
        revenue_today     = self.get_revenue_today()
        revenue_yesterday = self.get_revenue_yesterday()
        orders_today      = self.get_orders_today()
        orders_yesterday  = self.get_orders_yesterday()
        avg_order         = self.get_avg_order_value()

        # Calculate changes
        rev_change = 0
        if revenue_yesterday > 0:
            rev_change = (
                (revenue_today - revenue_yesterday)
                / revenue_yesterday * 100
            )

        ord_change = 0
        if orders_yesterday > 0:
            ord_change = (
                (orders_today - orders_yesterday)
                / orders_yesterday * 100
            )

        return {
            'kpis': {
                'revenue_today':     revenue_today,
                'revenue_yesterday': revenue_yesterday,
                'revenue_change':    round(rev_change, 1),
                'orders_today':      orders_today,
                'orders_yesterday':  orders_yesterday,
                'orders_change':     round(ord_change, 1),
                'avg_order_value':   round(avg_order, 2),
                'revenue_this_week': self.get_revenue_this_week(),
                'revenue_this_month': self.get_revenue_this_month(),
            },
            'by_channel':   self.get_revenue_by_channel(),
            'top_products': self.get_top_products(5),
            'daily_trend':  self.get_daily_trend(30),
            'anomalies':    self.detect_anomalies(),
            'forecast':     self.forecast_next_month(),
            'week_compare': self.compare_periods('week'),
            'generated_at': datetime.now().strftime(
                '%Y-%m-%d %H:%M:%S'
            )
        }


# Global instance
analytics = AnalyticsEngine()