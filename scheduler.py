from apscheduler.schedulers.background import BackgroundScheduler
from data_loader import load_all_files_in_folder, watcher
import atexit

def start_scheduler():
    # Start the file watcher
    # This watches data/ folder every 30 seconds
    # Any new CSV dropped in → auto loads to MySQL
    watcher.start()

    # Also run a full folder scan every 30 minutes
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=lambda: load_all_files_in_folder("data"),
        trigger='interval',
        minutes=30,
        id='full_scan',
        name='Full folder scan',
        replace_existing=True
    )
    scheduler.start()
    print("[Scheduler] ✅ Started — watching data/ folder")

    atexit.register(lambda: scheduler.shutdown())
    atexit.register(watcher.stop)

    return scheduler