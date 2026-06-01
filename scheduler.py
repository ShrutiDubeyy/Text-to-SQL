from apscheduler.schedulers.background \
    import BackgroundScheduler
from data_loader import load_all_files_in_folder
import atexit


def sync_google_sheets():
    try:
        from sheets_connector import sheets
        if sheets.is_available():
            sheets.sync_all_due()
    except Exception as e:
        print(f"[Scheduler] Sheets error: {e}")


def sync_csv_files():
    try:
        load_all_files_in_folder("data")
    except Exception as e:
        print(f"[Scheduler] CSV error: {e}")


def check_kpi_alerts():
    """Check KPI alerts every hour"""
    try:
        from alert_engine import alert_engine
        alert_engine.check_all_alerts()
    except Exception as e:
        print(f"[Scheduler] Alert error: {e}")


def generate_daily_briefing():
    """Generate briefing at 9am daily"""
    try:
        from proactive_analyst import proactive_analyst
        proactive_analyst.generate_daily_briefing()
    except Exception as e:
        print(f"[Scheduler] Briefing error: {e}")


def start_scheduler():
    scheduler = BackgroundScheduler()

    # Google Sheets every 5 mins
    scheduler.add_job(
        func=sync_google_sheets,
        trigger='interval', minutes=5,
        id='sheets_sync',
        replace_existing=True
    )

    # CSV files every 30 mins
    scheduler.add_job(
        func=sync_csv_files,
        trigger='interval', minutes=30,
        id='csv_sync',
        replace_existing=True
    )

    # KPI alerts every hour
    scheduler.add_job(
        func=check_kpi_alerts,
        trigger='interval', minutes=60,
        id='kpi_alerts',
        replace_existing=True
    )

    # Daily briefing at 9am
    scheduler.add_job(
        func=generate_daily_briefing,
        trigger='cron', hour=9, minute=0,
        id='daily_briefing',
        replace_existing=True
    )

    scheduler.start()
    print("[Scheduler] ✅ Started")
    print("[Scheduler] → Sheets:   every 5 mins")
    print("[Scheduler] → CSV:      every 30 mins")
    print("[Scheduler] → Alerts:   every hour")
    print("[Scheduler] → Briefing: daily at 9am")

    atexit.register(lambda: scheduler.shutdown())
    return scheduler