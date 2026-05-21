import customtkinter as ctk
import sqlite3
import re
from datetime import datetime
import winsound
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from PIL import Image
import pystray
import threading

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class Database:
    """Handles SQLite database operations and migrations."""

    def __init__(self, db_name='planner.db'):
        self.db_name = db_name
        self.init_db()
        self.migrate_db()  # Add missing columns if upgrading from older versions

    def init_db(self):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    day TEXT NOT NULL,
                    task_text TEXT NOT NULL,
                    task_time TEXT,
                    is_done BOOLEAN DEFAULT 0,
                    already_notified BOOLEAN DEFAULT 0,
                    task_type TEXT DEFAULT 'daily',
                    interval_seconds INTEGER DEFAULT 0,
                    last_notified_timestamp REAL DEFAULT 0
                )
            ''')
            conn.commit()

    def migrate_db(self):
        """Safely add new columns to existing table if they do not exist."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(tasks)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'task_type' not in columns:
                cursor.execute("ALTER TABLE tasks ADD COLUMN task_type TEXT DEFAULT 'daily'")
            if 'interval_seconds' not in columns:
                cursor.execute("ALTER TABLE tasks ADD COLUMN interval_seconds INTEGER DEFAULT 0")
            if 'last_notified_timestamp' not in columns:
                cursor.execute("ALTER TABLE tasks ADD COLUMN last_notified_timestamp REAL DEFAULT 0")

            conn.commit()

    def execute(self, query, params=()):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.fetchall()


db = Database()


class DayWindow(ctk.CTkToplevel):
    """UI window for managing daily tasks."""

    def __init__(self, parent, day_name):
        super().__init__(parent)
        self.day_name = day_name
        self.title(f"Tasks for {day_name}")
        self.geometry("400x800")

        self.tasks = []
        self._is_destroyed = False

        self.setup_ui()
        self.load_tasks()
        self.render_tasks()
        self.update_progress_circle()
        self.check_time()

        # Prevent memory leaks on window close
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_ui(self):
        self.entry = ctk.CTkEntry(self, placeholder_text="Task (e.g. Work 15:15)")
        self.entry.pack(fill="x", padx=20, pady=10)

        self.btn_add = ctk.CTkButton(self, text="ADD", command=self.add_task)
        self.btn_add.pack(pady=5)

        self.tasks_box = ctk.CTkTextbox(self, height=150)
        self.tasks_box.pack(fill="both", expand=False, padx=20, pady=10)

        self.btn_delete = ctk.CTkButton(self, text="DELETE LAST", fg_color="red", command=self.delete_last)
        self.btn_delete.pack(pady=5)

        self.progress_frame = ctk.CTkFrame(self, height=200)
        self.progress_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.fig, self.ax = plt.subplots(figsize=(4, 4), facecolor="#2E2E2E")
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.progress_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        self.reset = ctk.CTkButton(self, text="RESET: ✔", fg_color="#FF8C00", command=self.reset_done)
        self.reset.pack(padx=20, pady=10)

    def reset_done(self):
        db.execute("UPDATE tasks SET is_done = 0, already_notified = 0 WHERE day = ? AND task_type = 'daily'",
                   (self.day_name,))
        self.load_tasks()
        self.render_tasks()
        self.update_progress_circle()

    def parse_task(self, text):
        match = re.search(r"\d{2}:\d{2}", text)
        if match:
            time = match.group()
            clean_text = text.replace(time, "").strip()
            return clean_text, time
        return text, None

    def add_task(self):
        raw = self.entry.get().strip()
        if not raw: return
        text, time = self.parse_task(raw)

        db.execute('''
            INSERT INTO tasks (day, task_text, task_time, is_done, task_type)
            VALUES (?, ?, ?, 0, 'daily')
        ''', (self.day_name, text, time))

        self.entry.delete(0, "end")
        self.load_tasks()
        self.render_tasks()
        self.update_progress_circle()

    def delete_last(self):
        if not self.tasks: return
        db.execute("DELETE FROM tasks WHERE id = ?", (self.tasks[-1]["id"],))
        self.load_tasks()
        self.render_tasks()
        self.update_progress_circle()

    def update_task_status(self, task_id, is_done, already_notified):
        db.execute('UPDATE tasks SET is_done = ?, already_notified = ? WHERE id = ?',
                   (int(is_done), int(already_notified), task_id))

    def load_tasks(self):
        rows = db.execute('''
            SELECT id, task_text, task_time, is_done, already_notified 
            FROM tasks WHERE day = ? AND task_type = 'daily' ORDER BY id
        ''', (self.day_name,))

        self.tasks = [{
            "id": r[0], "text": r[1], "time": r[2], "done": bool(r[3]), "already_notified": bool(r[4])
        } for r in rows]

    def render_tasks(self):
        self.tasks_box.delete("1.0", "end")
        for i, task in enumerate(self.tasks, 1):
            status = "✔" if task["done"] else "☐"
            time_str = f"[{task['time']}]" if task['time'] else ""
            self.tasks_box.insert("end", f"{i}. {status} {task['text']} {time_str}\n")

    def update_progress_circle(self):
        total = len(self.tasks)
        done = len([t for t in self.tasks if t["done"]])
        self.ax.clear()
        if total > 0:
            undone = total - done
            self.ax.pie([done, undone], labels=["Done", "Undone"], textprops={'color': "white"},
                        colors=['#5676d7', '#324786'], startangle=90, autopct="%1.1f%%")
        else:
            self.ax.text(0.5, 0.5, "No tasks", color="white", ha='center')
        self.ax.set_title("Daily Progress", color="white")
        self.canvas.draw()

    def check_time(self):
        if self._is_destroyed: return
        current_day = datetime.now().strftime("%A")
        if self.day_name == current_day:
            now = datetime.now().strftime("%H:%M")
            for task in self.tasks:
                if task["time"] == now and not task["done"] and not task["already_notified"]:
                    task["already_notified"] = True
                    self.update_task_status(task["id"], task["done"], True)
                    self.notify(task)
        self.after(30000, self.check_time)

    def notify(self, task):
        try:
            winsound.PlaySound("study.wav", winsound.SND_FILENAME | winsound.SND_ASYNC)
        except:
            pass
        popup = ctk.CTkToplevel(self)
        popup.title("Task Reminder!")
        popup.geometry("300x200")
        popup.attributes("-topmost", True)

        def confirm(status):
            self.update_task_status(task["id"], status, True)
            self.load_tasks()
            self.render_tasks()
            self.update_progress_circle()
            popup.destroy()

        ctk.CTkLabel(popup, text=f"It's time for:\n{task['text']}", font=("Arial", 14)).pack(pady=20)
        ctk.CTkButton(popup, text="Completed", command=lambda: confirm(True)).pack(pady=5)
        ctk.CTkButton(popup, text="Skip", fg_color="red", command=lambda: confirm(False)).pack(pady=5)

    def on_close(self):
        self._is_destroyed = True
        plt.close(self.fig)  # Prevent matplotlib memory leak
        self.destroy()


class TimerWindow(ctk.CTkToplevel):
    """UI window for managing interval timers."""

    def __init__(self, parent, day_name):
        super().__init__(parent)
        self.day_name = day_name
        self.title(f"Timers for {day_name}")
        self.geometry("400x600")
        self.tasks = []
        self._is_destroyed = False

        self.installation_ui()
        self.load_mission()
        self.render_mission()
        self.check_moment()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def installation_ui(self):
        self.entry = ctk.CTkEntry(self, placeholder_text="Interval (Break 2h or 40min)")
        self.entry.pack(fill="x", padx=20, pady=10)
        ctk.CTkButton(self, text="ADD", command=self.add_mission).pack(pady=5)
        self.tasks_box = ctk.CTkTextbox(self, height=150)
        self.tasks_box.pack(fill="both", expand=False, padx=20, pady=10)
        ctk.CTkButton(self, text="DELETE LAST", fg_color="red", command=self.delete_past).pack(pady=5)

    def parse_mission(self, text):
        match = re.search(r"(\d+)h|(\d+)min", text)
        if match:
            time_val = match.group()
            seconds = int(re.findall(r'\d+', time_val)[0]) * (3600 if 'h' in time_val else 60)
            return text.replace(time_val, "").strip(), seconds
        return text, None

    def add_mission(self):
        raw = self.entry.get().strip()
        if not raw: return
        text, seconds = self.parse_mission(raw)
        if seconds is None: return

        db.execute('''
            INSERT INTO tasks (day, task_text, interval_seconds, last_notified_timestamp, task_type)
            VALUES (?, ?, ?, ?, 'timer')
        ''', (self.day_name, text, seconds, datetime.now().timestamp()))

        self.entry.delete(0, "end")
        self.load_mission()
        self.render_mission()

    def delete_past(self):
        if not self.tasks: return
        db.execute("DELETE FROM tasks WHERE id = ?", (self.tasks[-1]["id"],))
        self.load_mission()
        self.render_mission()

    def load_mission(self):
        rows = db.execute('''
            SELECT id, task_text, interval_seconds, last_notified_timestamp 
            FROM tasks WHERE day = ? AND task_type = 'timer' ORDER BY id
        ''', (self.day_name,))

        # Map rows to dict keys
        self.tasks = [{
            "id": r[0], "text": r[1], "interval": r[2], "last_notified_time": r[3]
        } for r in rows]

    def render_mission(self):
        self.tasks_box.delete("1.0", "end")
        for i, task in enumerate(self.tasks, 1):
            time_str = f"[{task['interval']} sec]" if task['interval'] else ""
            self.tasks_box.insert("end", f"{i}. ☐ {task['text']} {time_str}\n")

    def check_moment(self):
        if self._is_destroyed: return
        now_ts = datetime.now().timestamp()

        for task in self.tasks:
            interval = task["interval"]
            if interval and (now_ts - task["last_notified_time"] >= interval):
                self.notify(task)
                task["last_notified_time"] = now_ts
                db.execute('UPDATE tasks SET last_notified_timestamp = ? WHERE id = ?', (now_ts, task["id"]))

        self.after(30000, self.check_moment)

    def notify(self, task):
        try:
            winsound.PlaySound("study.wav", winsound.SND_FILENAME | winsound.SND_ASYNC)
        except:
            pass
        popup = ctk.CTkToplevel(self)
        popup.title("Interval Alert!")
        popup.geometry("300x150")
        popup.attributes("-topmost", True)
        ctk.CTkLabel(popup, text=f"Interval Alert:\n{task['text']}", font=("Arial", 14)).pack(pady=20)
        ctk.CTkButton(popup, text="OK", command=popup.destroy).pack(pady=5)

    def on_close(self):
        self._is_destroyed = True
        self.destroy()


class Daily(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.title("Daily Planner")
        self.geometry("800x300")
        self.main_container = None
        self.tray = None
        self.draw_button()
        self.create_tray_icon()
        self.protocol('WM_DELETE_WINDOW', self.hide_window)

    def reset_all_files(self):
        db.execute("UPDATE tasks SET is_done = 0, already_notified = 0 WHERE task_type = 'daily'")
        print("All database daily tasks reset!")
        self.draw_button()

    def draw_button(self):
        self.clear_screen()
        self.main_container = ctk.CTkFrame(self)
        self.main_container.pack(pady=10, fill="both", expand=True)

        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for i, day in enumerate(days):
            self.main_container.grid_columnconfigure(i, weight=1)
            ctk.CTkLabel(self.main_container, text=day).grid(row=0, column=i, pady=10)
            ctk.CTkButton(self.main_container, text="Open", width=100,
                          command=lambda d=day: DayWindow(self, d)).grid(row=1, column=i, padx=5, pady=5)

        ctk.CTkButton(self.main_container, text="Overdue Tasks", width=120,
                      command=self.Overdue_task).grid(row=3, column=0, columnspan=2, pady=20)

        current_day = datetime.now().strftime('%A')
        ctk.CTkButton(self.main_container, text="Timer", width=120,
                      command=lambda: TimerWindow(self, current_day)).grid(row=3, column=2, columnspan=2, pady=20)

        ctk.CTkButton(self.main_container, text="RESET ALL", width=120, fg_color="orange",
                      command=self.reset_all_files).grid(row=3, column=4, columnspan=2, pady=20)

    def clear_screen(self):
        if self.main_container:
            self.main_container.destroy()

    def Overdue_task(self):
        self.clear_screen()
        self.main_container = ctk.CTkFrame(self)
        self.main_container.pack(fill="both", expand=True)

        rows = db.execute("SELECT day, task_text FROM tasks WHERE is_done = 0 AND task_type = 'daily'")
        all_undone = [f"{row[0]}: {row[1]}" for row in rows]

        textbox = ctk.CTkTextbox(self.main_container, height=150)
        textbox.pack(pady=10, padx=10, fill="both")
        for item in all_undone:
            textbox.insert("end", item + "\n")
        ctk.CTkButton(self.main_container, text="Back", command=self.draw_button).pack(pady=5)

    def hide_window(self):
        self.withdraw()

    def safe_show_window(self):
        """Thread-safe window deiconification using after()."""
        self.after(0, self.deiconify)

    def quit_app(self):
        if self.tray:
            self.tray.stop()
        self.quit()  # Clean exit from mainloop()

    def create_tray_icon(self):
        icon_image = Image.new('RGB', (64, 64), color=(86, 118, 215))
        menu = pystray.Menu(
            pystray.MenuItem('Open', self.safe_show_window),
            pystray.MenuItem('Exit', self.quit_app)
        )
        self.tray = pystray.Icon("Daily", icon_image, "Daily Planner", menu)
        threading.Thread(target=self.tray.run, daemon=True).start()


if __name__ == "__main__":
    app = Daily()
    app.mainloop()
