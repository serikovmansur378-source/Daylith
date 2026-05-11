import customtkinter as ctk
import json
import os
from datetime import datetime
import winsound
import re
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from PIL import Image
import pystray
import threading

# Global UI configuration: setting the dark theme and color scheme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class DayWindow(ctk.CTkToplevel):
    """Window for managing tasks for a specific day"""

    def __init__(self, parent, day_name):
        super().__init__(parent)
        self.day_name = day_name
        self.file_name = f"{day_name}.json"
        self.title(f"Tasks for {day_name}")
        self.geometry("400x800")

        self.tasks = []
        self.setup_ui()
        self.load_tasks()
        self.render_tasks()
        self.update_progress_circle()
        self.check_time()

    def setup_ui(self):
        """Initialize the layout and widgets for the day window"""
        self.entry = ctk.CTkEntry(self, placeholder_text="Task (e.g. Work 15:15)")
        self.entry.pack(fill="x", padx=20, pady=10)

        self.btn_add = ctk.CTkButton(self, text="ADD", command=self.add_task)
        self.btn_add.pack(pady=5)

        self.tasks_box = ctk.CTkTextbox(self, height=150)
        self.tasks_box.pack(fill="both", expand=False, padx=20, pady=10)

        self.btn_delete = ctk.CTkButton(self, text="DELETE LAST", fg_color="red", command=self.delete_last)
        self.btn_delete.pack(pady=5)

        # Frame to hold the Matplotlib progress chart
        self.progress_frame = ctk.CTkFrame(self, height=200)
        self.progress_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # Setup Matplotlib figure for the pie chart
        self.fig, self.ax = plt.subplots(figsize=(4, 4), facecolor="#2E2E2E")
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.progress_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        self.reset = ctk.CTkButton(self, text="RESET: ✔", fg_color="#FF8C00", command=self.reset_done)
        self.reset.pack(padx=20, pady=10)

    def reset_done(self):
        """Uncheck all 'done' statuses for the current day"""
        for task in self.tasks:
            task["done"] = False
        self.render_tasks()
        self.update_progress_circle()
        self.save_tasks()

    def parse_task(self, text):
        """Extract time (HH:MM) from the input string using regex"""
        match = re.search(r"\d{2}:\d{2}", text)
        if match:
            time = match.group()
            clean_text = text.replace(time, "").strip()
            return clean_text, time
        return text, None

    def add_task(self):
        """Get input, parse it, and add to the task list"""
        raw = self.entry.get().strip()
        if not raw: return
        text, time = self.parse_task(raw)
        self.tasks.append({"text": text, "time": time, "done": False})
        self.entry.delete(0, "end")
        self.save_tasks()
        self.render_tasks()
        self.update_progress_circle()

    def delete_last(self):
        """Remove the most recently added task"""
        if self.tasks:
            self.tasks.pop()
            self.save_tasks()
            self.render_tasks()
            self.update_progress_circle()

    def save_tasks(self):
        """Serialize task list to a JSON file"""
        with open(self.file_name, "w", encoding="utf-8") as f:
            json.dump(self.tasks, f, ensure_ascii=False, indent=2)

    def load_tasks(self):
        """Load tasks from JSON file if it exists"""
        if os.path.exists(self.file_name):
            with open(self.file_name, "r", encoding="utf-8") as f:
                self.tasks = json.load(f)
        # Automatic reset logic for Sundays
        if datetime.now().weekday() == 6:
            for task in self.tasks:
                task["done"] = False

    def render_tasks(self):
        """Update the UI textbox with current tasks and their status"""
        self.tasks_box.delete("1.0", "end")
        for i, task in enumerate(self.tasks, 1):
            status = "✔" if task.get("done") else "☐"
            time_str = f"[{task['time']}]" if task['time'] else ""
            line = f"{i}. {status} {task['text']} {time_str}\n"
            self.tasks_box.insert("end", line)

    def update_progress_circle(self):
        """Generate and draw a pie chart showing task completion ratio"""
        total = len(self.tasks)
        done = len([t for t in self.tasks if t.get("done")])
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
        """Background loop to check if it's time for any pending task"""
        current_day = datetime.now().strftime("%A")
        if self.day_name == current_day:
            now = datetime.now().strftime("%H:%M")
            for task in self.tasks:
                if task["time"] == now and not task.get("done") and not task.get("already_notified"):
                    self.notify(task)
                    task["already_notified"] = True
        # Run this check every 30 seconds
        self.after(30000, self.check_time)

    def notify(self, task):
        """Play sound and show a 'TopMost' popup window for reminders"""
        try:
            winsound.PlaySound("study.wav", winsound.SND_FILENAME | winsound.SND_ASYNC)
        except:
            pass
        popup = ctk.CTkToplevel(self)
        popup.title("Task Reminder!")
        popup.geometry("300x200")
        popup.attributes("-topmost", True)

        def confirm(status):
            task["done"] = status
            self.save_tasks()
            self.render_tasks()
            self.update_progress_circle()
            popup.destroy()

        ctk.CTkLabel(popup, text=f"It's time for:\n{task['text']}", font=("Arial", 14)).pack(pady=20)
        ctk.CTkButton(popup, text="Completed", command=lambda: confirm(True)).pack(pady=5)
        ctk.CTkButton(popup, text="Skip", fg_color="red", command=lambda: confirm(False)).pack(pady=5)


class TimerWindow(ctk.CTkToplevel):
    """Window for handling recurring interval-based timers"""
    def __init__(self, parent, day_name):
        super().__init__(parent)
        self.day_name = day_name
        self.file_name = f"timer_{day_name}.json"
        self.title(f"Timers for {day_name}")
        self.geometry("400x600")
        self.tasks = []
        self.installation_ui()
        self.load_mission()
        self.render_mission()
        self.check_moment()

    def installation_ui(self):
        """Build the UI for the timer/interval management"""
        self.entry = ctk.CTkEntry(self, placeholder_text="Interval (Break 2h/ or 40min)")
        self.entry.pack(fill="x", padx=20, pady=10)
        ctk.CTkButton(self, text="ADD", command=self.add_mission).pack(pady=5)
        self.tasks_box = ctk.CTkTextbox(self, height=150)
        self.tasks_box.pack(fill="both", expand=False, padx=20, pady=10)
        ctk.CTkButton(self, text="DELETE LAST", fg_color="red", command=self.delete_past).pack(pady=5)

    def delete_past(self):
        """Remove the last timer entry"""
        if self.tasks:
            self.tasks.pop()
            self.save_mission()
            self.render_mission()

    def parse_mission(self, text):
        """Parse 'h' or 'min' input and convert it to total seconds"""
        match = re.search(r"(\d+)h|(\d+)min", text)
        if match:
            time_val = match.group()
            seconds = int(re.findall(r'\d+', time_val)[0]) * (3600 if 'h' in time_val else 60)
            return text.replace(time_val, "").strip(), seconds
        return text, None

    def add_mission(self):
        """Add a new interval mission to the list"""
        raw = self.entry.get().strip()
        if not raw: return
        text, time = self.parse_mission(raw)
        self.tasks.append({"text": text, "time": time, "done": False})
        self.entry.delete(0, "end")
        self.save_mission()
        self.render_mission()

    def render_mission(self):
        """Update the textbox display with interval missions"""
        self.tasks_box.delete("1.0", "end")
        for i, task in enumerate(self.tasks, 1):
            status = "✔" if task.get("done") else "☐"
            time_str = f"[{task['time']} sec]" if task.get('time') else ""
            self.tasks_box.insert("end", f"{i}. {status} {task['text']} {time_str}\n")

    def check_moment(self):
        """Check if the time interval has passed since the last notification"""
        now_ts = datetime.now().timestamp()
        for task in self.tasks:
            interval = task.get("time")
            if isinstance(interval, (int, float)):
                if "last_notified_time" not in task:
                    task["last_notified_time"] = now_ts
                if now_ts - task["last_notified_time"] >= interval:
                    self.notify(task)
                    task["last_notified_time"] = now_ts
                    self.save_mission()
        self.after(30000, self.check_moment)

    def save_mission(self):
        """Save timer data to JSON"""
        with open(self.file_name, "w", encoding="utf-8") as f:
            json.dump(self.tasks, f, ensure_ascii=False, indent=2)

    def load_mission(self):
        """Load timer data from JSON"""
        if os.path.exists(self.file_name):
            with open(self.file_name, "r", encoding="utf-8") as f:
                self.tasks = json.load(f)

    def notify(self, task):
        """Standard alert for recurring intervals"""
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


class Daily(ctk.CTk):
    """Main application window for the Daily Planner"""
    def __init__(self):
        super().__init__()
        self.title("Daily Planner")
        self.geometry("800x300")
        self.main_container = None
        self.tray = None
        self.draw_button()
        self.create_tray_icon()
        # Ensure 'X' button hides the window to the tray instead of closing it
        self.protocol('WM_DELETE_WINDOW', self.hide_window)

    def reset_all_files(self):
        """Reset 'done' status for all tasks across all JSON files"""
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for day in days:
            filename = f"{day}.json"
            if os.path.exists(filename):
                with open(filename, "r", encoding="utf-8") as f:
                    tasks = json.load(f)
                for task in tasks:
                    task["done"] = False
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(tasks, f, ensure_ascii=False, indent=4)
        print("All days reset!")
        self.draw_button()  # Refresh main UI

    def draw_button(self):
        """Render the main menu buttons for days and utilities"""
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
        """Destroy the current container to make space for a new one"""
        if self.main_container:
            self.main_container.destroy()

    def Overdue_task(self):
        """Scan all day files and display tasks that are not yet marked as 'done'"""
        self.clear_screen()
        self.main_container = ctk.CTkFrame(self)
        self.main_container.pack(fill="both", expand=True)

        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        all_undone = []
        for day in days:
            file_name = f"{day}.json"
            if os.path.exists(file_name):
                with open(file_name, "r", encoding="utf-8") as f:
                    tasks = json.load(f)
                    for t in tasks:
                        if not t.get("done"):
                            all_undone.append(f"{day}: {t['text']}")

        textbox = ctk.CTkTextbox(self.main_container, height=150)
        textbox.pack(pady=10, padx=10, fill="both")
        for item in all_undone:
            textbox.insert("end", item + "\n")
        ctk.CTkButton(self.main_container, text="Back", command=self.draw_button).pack(pady=5)

    def hide_window(self):
        """Minimize the application window from view"""
        self.withdraw()

    def show_window(self):
        """Restore the application window from the tray"""
        self.deiconify()

    def quit_app(self):
        """Stop the tray icon thread and shut down the application"""
        if self.tray:
            self.tray.stop()
        self.destroy()

    def create_tray_icon(self):
        """Initialize the system tray icon using a separate thread"""
        icon_image = Image.new('RGB', (64, 64), color=(86, 118, 215))
        menu = pystray.Menu(
            pystray.MenuItem('Open', self.show_window),
            pystray.MenuItem('Exit', self.quit_app)
        )
        self.tray = pystray.Icon("Daily", icon_image, "Daily Planner", menu)
        # Threading is required so pystray doesn't block the main Tkinter loop
        threading.Thread(target=self.tray.run, daemon=True).start()

if __name__ == "__main__":
    app = Daily()
    app.mainloop()