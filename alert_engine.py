import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from db import get_connection
from analytics_engine import analytics
import os


class AlertEngine:
    """
    KPI monitoring and alert system.
    Checks rules every hour.
    Sends email when threshold breached.
    """

    def __init__(self):
        self.smtp_host = os.getenv(
            'SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv(
            'SMTP_PORT', '587'))
        self.smtp_user = os.getenv('SMTP_USER', '')
        self.smtp_pass = os.getenv('SMTP_PASS', '')

    def add_alert(self, user_id, alert_name,
                  metric, operator, threshold,
                  time_window='today', email=None):
        """Create a new KPI alert rule"""
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO kpi_alerts
                (user_id, alert_name, metric,
                 operator, threshold,
                 time_window, email)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (user_id, alert_name, metric,
                  operator, threshold,
                  time_window, email))
            conn.commit()
            cursor.close()
            conn.close()
            print(f"[Alert] Created: {alert_name}")
            return True
        except Exception as e:
            print(f"[Alert] Create error: {e}")
            return False

    def get_alerts(self, user_id=None):
        """Get all alert rules"""
        try:
            conn   = get_connection()
            cursor = conn.cursor(dictionary=True)
            if user_id:
                cursor.execute("""
                    SELECT * FROM kpi_alerts
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT * FROM kpi_alerts
                    ORDER BY created_at DESC
                """)
            alerts = cursor.fetchall()
            cursor.close()
            conn.close()
            for a in alerts:
                for k, v in a.items():
                    if hasattr(v, 'strftime'):
                        a[k] = v.strftime(
                            '%Y-%m-%d %H:%M:%S')
            return alerts
        except Exception as e:
            print(f"[Alert] Get error: {e}")
            return []

    def delete_alert(self, alert_id):
        """Delete an alert rule"""
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM kpi_alerts WHERE id=%s",
                (alert_id,))
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"[Alert] Delete error: {e}")
            return False

    def _get_metric_value(self, metric,
                          time_window='today'):
        """Get current value of a metric"""
        metric_map = {
            'revenue':    analytics.get_revenue_today,
            'orders':     analytics.get_orders_today,
            'avg_order':  analytics.get_avg_order_value,
            'revenue_week': analytics.get_revenue_this_week,
            'revenue_month': analytics.get_revenue_this_month,
        }

        func = metric_map.get(metric)
        if func:
            return func()
        return None

    def _check_condition(self, value,
                         operator, threshold):
        """Check if alert condition is met"""
        ops = {
            'less_than':       value < threshold,
            'greater_than':    value > threshold,
            'less_equal':      value <= threshold,
            'greater_equal':   value >= threshold,
            'equals':          value == threshold,
        }
        return ops.get(operator, False)

    def _already_sent_today(self, alert_id):
        """Prevent duplicate alerts"""
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM alert_history
                WHERE alert_id = %s
                AND DATE(sent_at) = CURDATE()
            """, (alert_id,))
            count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return count > 0
        except Exception:
            return False

    def _log_alert(self, alert_id, alert_name,
                   value, threshold, message):
        """Log alert to history"""
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO alert_history
                (alert_id, alert_name,
                 metric_value, threshold, message)
                VALUES (%s,%s,%s,%s,%s)
            """, (alert_id, alert_name,
                  value, threshold, message))

            cursor.execute("""
                UPDATE kpi_alerts
                SET last_triggered = NOW(),
                    trigger_count = trigger_count + 1
                WHERE id = %s
            """, (alert_id,))

            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[Alert] Log error: {e}")

    def send_email_alert(self, to_email,
                         subject, body):
        """Send email alert"""
        if not self.smtp_user or not self.smtp_pass:
            print(f"[Alert] Email not configured. "
                  f"Alert: {subject}")
            return False

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From']    = self.smtp_user
            msg['To']      = to_email

            html_body = f"""
            <div style="font-family:sans-serif;
                        max-width:600px;
                        margin:0 auto;padding:20px">
              <h2 style="color:#ef4444;">
                ⚠️ KPI Alert Triggered
              </h2>
              <div style="background:#fef2f2;
                          padding:16px;
                          border-radius:8px;
                          border-left:4px solid #ef4444;">
                {body}
              </div>
              <p style="color:#64748b;font-size:12px;
                        margin-top:20px;">
                Sent by your Data Analyst Bot
              </p>
            </div>
            """

            msg.attach(MIMEText(html_body, 'html'))

            server = smtplib.SMTP(
                self.smtp_host, self.smtp_port)
            server.starttls()
            server.login(
                self.smtp_user, self.smtp_pass)
            server.sendmail(
                self.smtp_user, to_email,
                msg.as_string())
            server.quit()

            print(f"[Alert] Email sent to {to_email}")
            return True

        except Exception as e:
            print(f"[Alert] Email error: {e}")
            return False

    def check_all_alerts(self):
        """
        Check all active alert rules.
        Called every hour by scheduler.
        """
        try:
            conn   = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM kpi_alerts
                WHERE is_active = TRUE
            """)
            alerts = cursor.fetchall()
            cursor.close()
            conn.close()

        except Exception as e:
            print(f"[Alert] Check error: {e}")
            return

        triggered = 0

        for alert in alerts:
            try:
                value = self._get_metric_value(
                    alert['metric'],
                    alert['time_window']
                )

                if value is None:
                    continue

                breached = self._check_condition(
                    value,
                    alert['operator'],
                    float(alert['threshold'])
                )

                if not breached:
                    continue

                if self._already_sent_today(
                        alert['id']):
                    continue

                message = (
                    f"<b>{alert['alert_name']}</b><br>"
                    f"Current value: "
                    f"<b>${value:,.2f}</b><br>"
                    f"Threshold: "
                    f"${float(alert['threshold']):,.2f}"
                    f" ({alert['operator']})<br>"
                    f"Time: "
                    f"{datetime.now().strftime('%H:%M')}"
                )

                self._log_alert(
                    alert['id'],
                    alert['alert_name'],
                    value,
                    alert['threshold'],
                    message
                )

                if alert.get('email'):
                    self.send_email_alert(
                        alert['email'],
                        f"⚠️ Alert: {alert['alert_name']}",
                        message
                    )

                triggered += 1
                print(f"[Alert] Triggered: "
                      f"{alert['alert_name']} "
                      f"(value: {value})")

            except Exception as e:
                print(f"[Alert] Rule error: {e}")

        if triggered:
            print(f"[Alert] {triggered} alerts fired")

    def get_alert_history(self, limit=50):
        """Get recent alert history"""
        try:
            conn   = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM alert_history
                ORDER BY sent_at DESC
                LIMIT %s
            """, (limit,))
            history = cursor.fetchall()
            cursor.close()
            conn.close()
            for h in history:
                if h.get('sent_at'):
                    h['sent_at'] = h['sent_at']\
                        .strftime('%Y-%m-%d %H:%M:%S')
            return history
        except Exception as e:
            print(f"[Alert] History error: {e}")
            return []


alert_engine = AlertEngine()