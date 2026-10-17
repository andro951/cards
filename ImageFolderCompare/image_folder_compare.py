"""Small Windows UI for comparing two image exports."""
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from compare_core import Cancelled, compare_sets, discover, existing_outputs


class CompareApp:
    def __init__(self, root):
        self.root = root
        root.title("Image Folder Compare")
        root.geometry("820x455")
        root.minsize(680, 440)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.closing = False
        self.candidates = []
        self.parent_folder = None
        self.folder = tk.StringVar()
        self.older = tk.StringVar()
        self.newer = tk.StringVar()
        self.status = tk.StringVar(value="Choose a folder containing two image folders or ZIP files.")
        self.summary = tk.StringVar(value="")
        self.controls = []
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        root.option_add("*Font", ("Segoe UI", 10))
        panel = ttk.Frame(root, padding=22)
        panel.pack(fill="both", expand=True)
        panel.columnconfigure(0, weight=1)
        ttk.Label(panel, text="Compare image exports", font=("Segoe UI", 17, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(panel, text="Review images: generated half only. Other images: all pixels.").grid(row=1, column=0, sticky="w", pady=(4, 18))

        folder_row = ttk.Frame(panel)
        folder_row.grid(row=2, column=0, sticky="ew")
        folder_row.columnconfigure(0, weight=1)
        entry = ttk.Entry(folder_row, textvariable=self.folder)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        entry.bind("<Return>", lambda event: self.scan())
        self.controls.append(entry)
        self.button(folder_row, "Browse…", self.browse).grid(row=0, column=1, padx=(0, 8))
        self.button(folder_row, "Scan", self.scan).grid(row=0, column=2)

        choices = ttk.Frame(panel)
        choices.grid(row=3, column=0, sticky="ew", pady=(18, 10))
        choices.columnconfigure(1, weight=1)
        ttk.Label(choices, text="Older set", width=11).grid(row=0, column=0, sticky="w", pady=5)
        ttk.Label(choices, text="Newer set", width=11).grid(row=1, column=0, sticky="w", pady=5)
        self.old_box = ttk.Combobox(choices, textvariable=self.older, state="readonly")
        self.new_box = ttk.Combobox(choices, textvariable=self.newer, state="readonly")
        self.old_box.grid(row=0, column=1, sticky="ew", pady=5)
        self.new_box.grid(row=1, column=1, sticky="ew", pady=5)
        self.controls.extend((self.old_box, self.new_box))
        self.button(choices, "Swap", self.swap).grid(row=0, column=2, rowspan=2, padx=(12, 0))
        ttk.Label(panel, text="Matched by relative filename. Subfolders named removed, diff, and new are ignored.",
                  wraplength=740).grid(row=4, column=0, sticky="w", pady=(0, 14))

        actions = ttk.Frame(panel)
        actions.grid(row=5, column=0, sticky="ew")
        self.button(actions, "Compare images", self.compare).pack(side="left")
        self.cancel_button = ttk.Button(actions, text="Cancel", command=self.cancel.set, state="disabled")
        self.cancel_button.pack(side="left", padx=8)
        self.open_button = ttk.Button(actions, text="Open results folder", command=self.open_results, state="disabled")
        self.open_button.pack(side="right")
        self.progress = ttk.Progressbar(panel, mode="determinate")
        self.progress.grid(row=6, column=0, sticky="ew", pady=(18, 10))
        ttk.Label(panel, textvariable=self.status, wraplength=740).grid(row=7, column=0, sticky="w")
        ttk.Label(panel, textvariable=self.summary, font=("Segoe UI", 11, "bold"), wraplength=740).grid(row=8, column=0, sticky="w", pady=(10, 0))
        root.after(60, self.poll)

    def button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=command)
        self.controls.append(button)
        return button

    def browse(self):
        path = filedialog.askdirectory(title="Folder containing the two image exports", initialdir=self.folder.get() or None)
        if path:
            self.folder.set(path)
            self.scan()

    def run(self, operation, name):
        if self.busy:
            return
        self.busy = True
        self.cancel.clear()
        self.summary.set("")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.open_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        for control in self.controls:
            control.configure(state="disabled")

        def worker():
            try:
                value = operation()
                self.events.put((name, value))
            except Cancelled:
                self.events.put(("cancelled", None))
            except Exception as error:
                self.events.put(("error", str(error)))

        threading.Thread(target=worker, daemon=True).start()

    def scan(self):
        if self.busy:
            return
        folder = Path(self.folder.get()).expanduser()
        if not self.folder.get().strip() or not folder.is_dir():
            messagebox.showerror("Choose a folder", "Select the parent folder containing the image folders or ZIP files.")
            return
        self.parent_folder = folder.resolve()
        self.status.set("Finding image folders and ZIP files…")
        self.run(lambda: discover(self.parent_folder, self.cancel), "scanned")

    def swap(self):
        old, new = self.older.get(), self.newer.get()
        self.older.set(new)
        self.newer.set(old)

    def compare(self):
        if self.busy:
            return
        if self.parent_folder is None or Path(self.folder.get()).expanduser().resolve() != self.parent_folder:
            self.scan()
            return
        selected = {item.label: item for item in self.candidates}
        old, new = selected.get(self.older.get()), selected.get(self.newer.get())
        if old is None or new is None or old.path == new.path:
            messagebox.showerror("Choose two sets", "Choose a different older and newer image set. Use Scan if the folder has changed.")
            return
        try:
            previous = existing_outputs(self.parent_folder)
        except ValueError as error:
            messagebox.showerror("Output folder unavailable", str(error))
            return
        if previous and not messagebox.askyesno("Replace previous results?",
                "Replace the existing contents of diff, new, and removed with this comparison?\n\nThe two source image sets will be kept untouched."):
            return
        last_report = 0

        def progress(text, current, total):
            nonlocal last_report
            now = time.monotonic()
            if now - last_report > .06 or (total and current == total):
                self.events.put(("progress", (text, current, total)))
                last_report = now

        self.status.set("Preparing image sets…")
        self.run(lambda: compare_sets(self.parent_folder, old, new, replace_existing=bool(previous),
                                     cancel=self.cancel, progress=progress), "compared")

    def finish(self):
        self.busy = False
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=1, value=0)
        self.cancel_button.configure(state="disabled")
        for control in self.controls:
            control.configure(state="readonly" if isinstance(control, ttk.Combobox) else "normal")

    def poll(self):
        while not self.events.empty():
            name, value = self.events.get_nowait()
            if name == "progress":
                text, current, total = value
                self.status.set(text)
                if total:
                    self.progress.stop()
                    self.progress.configure(mode="determinate", maximum=total, value=current)
                continue
            self.finish()
            if self.closing:
                self.root.destroy()
                return
            if name == "scanned":
                self.candidates = value
                labels = [item.label for item in value]
                self.old_box.configure(values=labels)
                self.new_box.configure(values=labels)
                self.older.set(labels[-2] if len(labels) >= 2 else "")
                self.newer.set(labels[-1] if len(labels) >= 2 else "")
                self.status.set(f"Found {len(labels)} image sets. Older/newer selected by modification time; use Swap if needed."
                                if len(labels) >= 2 else "Need two image folders or ZIP files inside this folder.")
            elif name == "compared":
                self.progress.configure(value=1)
                self.status.set(f"Finished in {value.elapsed:.2f} seconds. Results saved in {self.parent_folder}")
                self.summary.set(f"Changed: {value.changed:,}    New: {value.added:,}    Removed: {value.removed:,}    Unchanged: {value.unchanged:,}")
                self.open_button.configure(state="normal")
            elif name == "cancelled":
                self.status.set("Cancelled. Previous results were kept.")
            elif name == "error":
                self.status.set("Comparison stopped. See error details.")
                messagebox.showerror("Image Folder Compare", value)
        self.root.after(60, self.poll)

    def open_results(self):
        if self.parent_folder and self.parent_folder.is_dir():
            os.startfile(self.parent_folder)

    def close(self):
        if self.busy:
            self.closing = True
            self.cancel.set()
            self.status.set("Cancelling and closing…")
        else:
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    CompareApp(root)
    root.mainloop()
