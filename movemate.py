import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import shutil
import subprocess
import ctypes
import threading
import sys
import time
import re
from datetime import datetime
import json
from pathlib import Path

try:
    import ttkbootstrap as bs
    from ttkbootstrap.constants import *
    HAS_TTKBOOTSTRAP = True
except ImportError:
    HAS_TTKBOOTSTRAP = False

BOTH = "both"; YES = "yes"; NORMAL = "normal"; DISABLED = "disabled"
END = "end"; EW = "ew"; NS = "ns"; NSEW = "nsew"; W = "w"; E = "e"
LEFT = "left"; RIGHT = "right"; HORIZONTAL = "horizontal"
VERTICAL = "vertical"; CENTER = "center"; X = "x"

def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def is_symlink(path):
    try:
        return os.path.islink(path)
    except Exception:
        return False

class TransferHistory:
    def __init__(self, filepath="movemate_history.json"):
        self.filepath = filepath
        self.records = self._load()

    def _load(self):
        try:
            if os.path.exists(self.filepath):
                with open(self.filepath, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def save(self):
        try:
            with open(self.filepath, "w") as f:
                json.dump(self.records, f, indent=2)
        except Exception:
            pass

    def add(self, source, dest, had_symlink):
        self.records.append({
            "source": source,
            "dest": dest,
            "had_symlink": had_symlink,
            "timestamp": datetime.now().isoformat(),
        })
        self.save()

    def remove(self, dest):
        self.records = [r for r in self.records if r["dest"] != dest]
        self.save()

class RobocopyMover:
    def __init__(self, source, dest, progress_cb=None, stop_event=None):
        self.source = source
        self.dest = dest
        self.progress_cb = progress_cb or (lambda **_: None)
        self.stop_event = stop_event or threading.Event()

    def _same_drive(self):
        try:
            return (os.path.splitdrive(self.source)[0].upper() ==
                    os.path.splitdrive(self.dest)[0].upper())
        except Exception:
            return False

    def move(self):
        if self._same_drive():
            self._move_same_drive()
        else:
            self._move_cross_drive()
        return True

    def _move_same_drive(self):
        self.progress_cb(percent=0, speed="", eta="", files="")
        shutil.move(self.source, self.dest)
        self.progress_cb(percent=100, speed="", eta="", files="")

    def _move_cross_drive(self):
        cmd = [
            "robocopy",
            self.source, self.dest,
            "/E", "/COPYALL", "/R:1", "/W:1",
            "/NJH", "/NJS",
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        start_time = time.time()
        pct_pattern = re.compile(r"(\d+\.?\d*)\s*%")

        for line in proc.stdout:
            if self.stop_event.is_set():
                proc.terminate()
                raise RuntimeError("Stopped by user")

            line = line.strip()
            m = pct_pattern.search(line)
            if m:
                pct = float(m.group(1))
                elapsed = time.time() - start_time
                speed_str = ""
                eta_str = ""
                if elapsed > 1 and pct > 0:
                    eta_sec = (elapsed / pct) * (100 - pct)
                    eta_str = self._fmt_time(eta_sec)
                    pct_per_sec = pct / elapsed
                    speed_str = f"{pct_per_sec:.1f}%/s"
                self.progress_cb(percent=pct, speed=speed_str, eta=eta_str, files=line)

        proc.wait()
        rc = proc.returncode
        if rc >= 8:
            raise RuntimeError(f"robocopy failed (exit code {rc})")

        self.progress_cb(percent=99, speed="", eta="Cleaning up...", files="")
        shutil.rmtree(self.source)
        self.progress_cb(percent=100, speed="", eta="", files="")

    @staticmethod
    def _fmt_time(seconds):
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}h {m}m"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"

class FolderMoverApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MoveMate")
        self.root.geometry("720x640")
        self.root.minsize(660, 560)

        if not HAS_TTKBOOTSTRAP:
            self.root.configure(bg="#f8f9fa")

        self.queue = []
        self.queue_lock = threading.Lock()
        self.is_moving = False
        self.is_paused = False
        self.current_operation = ""
        self.operation_start_time = None
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.stop_event = threading.Event()

        self._item_percent = 0.0
        self._item_speed = ""
        self._item_eta = ""

        self.history = TransferHistory()
        self.settings_file = "filemover_settings.json"
        self.settings = self._load_settings()

        self.style = bs.Style() if HAS_TTKBOOTSTRAP else ttk.Style()
        self._configure_styles()
        self._create_widgets()
        self._create_context_menu()
        self._update_status_loop()

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _load_settings(self):
        defaults = {
            "last_source_dir": str(Path.home()),
            "default_destination": "",
            "window_geometry": "720x640",
        }
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r") as f:
                    defaults.update(json.load(f))
        except Exception:
            pass
        return defaults

    def _save_settings(self):
        try:
            if self.root.state() == "normal":
                self.settings["window_geometry"] = self.root.geometry()
            self.settings["default_destination"] = self.dest_path_var.get()
            with open(self.settings_file, "w") as f:
                json.dump(self.settings, f, indent=2)
        except Exception:
            pass

    def _on_closing(self):
        if self.is_moving:
            if messagebox.askyesno("Operation in Progress",
                                   "A transfer is running. Stop and exit?"):
                self.stop_event.set()
                self.pause_event.set()
                time.sleep(0.5)
            else:
                return
        self._save_settings()
        self.root.destroy()

    def _configure_styles(self):
        if HAS_TTKBOOTSTRAP:
            self.style.configure("Card.TLabelframe", padding=8, relief="flat", borderwidth=1)
            self.style.configure("Card.TLabelframe.Label", font=("Segoe UI", 8, "bold"))
            self.style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"),
                                 foreground=self.style.colors.primary)
            self.style.configure("Subtitle.TLabel", font=("Segoe UI", 8),
                                 foreground=self.style.colors.secondary)
            self.style.configure("Speed.TLabel", font=("Segoe UI", 8, "bold"),
                                 foreground=self.style.colors.info)
        else:
            s = self.style
            s.configure("TFrame", background="#f8f9fa")
            s.configure("TLabel", background="#f8f9fa", font=("Segoe UI", 8))
            s.configure("TLabelframe", background="#ffffff", padding=8,
                        relief="solid", borderwidth=1)
            s.configure("TLabelframe.Label", background="#ffffff",
                        font=("Segoe UI", 8, "bold"), foreground="#495057")
            s.configure("TButton", font=("Segoe UI", 8), padding=(8, 3))
            s.configure("TEntry", padding=4, font=("Segoe UI", 8))
            s.configure("Header.TLabel", font=("Segoe UI", 14, "bold"),
                        foreground="#007bff", background="#f8f9fa")
            s.configure("Subtitle.TLabel", font=("Segoe UI", 8),
                        foreground="#6c757d", background="#f8f9fa")
            s.configure("Speed.TLabel", font=("Segoe UI", 8, "bold"),
                        foreground="#17a2b8", background="#f8f9fa")

    def _cs(self):
        return "Card.TLabelframe" if HAS_TTKBOOTSTRAP else "TLabelframe"

    def _bs(self, variant=""):
        if HAS_TTKBOOTSTRAP and variant:
            return f"{variant}.TButton"
        return "TButton"

    def _create_widgets(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=BOTH, expand=YES, padx=12, pady=12)

        self.tab_move = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_move, text="  📦 Move  ")

        self.tab_restore = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_restore, text="  🔄 Restore  ")

        self._build_move_tab(self.tab_move)
        self._build_restore_tab(self.tab_restore)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def _build_move_tab(self, parent):
        parent.rowconfigure(3, weight=1)
        parent.columnconfigure(0, weight=1)
        self._create_header(parent)
        self._create_destination_section(parent)
        self._create_input_section(parent)
        self._create_queue_section(parent)
        self._create_control_section(parent)

    def _create_header(self, parent):
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=0, sticky=EW, pady=(0, 8))
        frame.columnconfigure(1, weight=1)

        tf = ttk.Frame(frame)
        tf.grid(row=0, column=0, sticky=W)
        ttk.Label(tf, text="📁", font=("Segoe UI", 16)).pack(side=LEFT, padx=(0, 8))
        ttk.Label(tf, text="MoveMate", style="Header.TLabel").pack(side=LEFT)

        admin_text = "🛡️ Admin" if is_admin() else "⚠️ User (no symlinks)"
        admin_color = "#28a745" if is_admin() else "#ffc107"
        ttk.Label(frame, text=admin_text, font=("Segoe UI", 7, "bold"),
                  foreground=admin_color).grid(row=0, column=1, sticky=E)

        ttk.Label(frame, text="Move folders & create symbolic links",
                  style="Subtitle.TLabel").grid(row=1, column=0, columnspan=2,
                                                sticky=W, pady=(2, 0))

    def _create_destination_section(self, parent):
        frame = ttk.Labelframe(parent, text="📍 Default Destination", style=self._cs())
        frame.grid(row=1, column=0, sticky=EW, pady=(0, 8))
        frame.columnconfigure(0, weight=1)

        inner = ttk.Frame(frame)
        inner.pack(fill=X)
        inner.columnconfigure(0, weight=1)

        self.dest_path_var = tk.StringVar(value=self.settings.get("default_destination", ""))
        e = ttk.Entry(inner, textvariable=self.dest_path_var)
        e.grid(row=0, column=0, sticky=EW, padx=(0, 6))
        e.bind("<KeyRelease>", self._validate_paths)

        ttk.Button(inner, text="📂", width=4, command=self._browse_dest).grid(row=0, column=1)

    def _create_input_section(self, parent):
        frame = ttk.Labelframe(parent, text="📁 Add Source Folder", style=self._cs())
        frame.grid(row=2, column=0, sticky=EW, pady=(0, 8))
        frame.columnconfigure(0, weight=1)

        pf = ttk.Frame(frame)
        pf.pack(fill=X, pady=(0, 6))
        pf.columnconfigure(0, weight=1)

        self.source_var = tk.StringVar()
        se = ttk.Entry(pf, textvariable=self.source_var)
        se.grid(row=0, column=0, sticky=EW, padx=(0, 6))
        se.bind("<KeyRelease>", self._validate_paths)

        self.source_browse_btn = ttk.Button(pf, text="📂", width=4, command=self._browse_source)
        self.source_browse_btn.grid(row=0, column=1)

        bf = ttk.Frame(frame)
        bf.pack(fill=X)
        bf.columnconfigure(0, weight=1)

        self.validation_label = ttk.Label(bf,
                                          text="💡 Set destination, then choose source folder",
                                          font=("Segoe UI", 7))
        self.validation_label.grid(row=0, column=0, sticky=W)

        self.add_btn = ttk.Button(bf, text="➕ Add to Queue",
                                  command=self._add_to_queue,
                                  style=self._bs("success"), state=DISABLED)
        self.add_btn.grid(row=0, column=1, sticky=E)

    def _create_queue_section(self, parent):
        frame = ttk.Labelframe(parent, text="📋 Transfer Queue", style=self._cs())
        frame.grid(row=3, column=0, sticky=NSEW, pady=(0, 8))
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        hdr = ttk.Frame(frame)
        hdr.pack(fill=X, pady=(0, 6))

        self.queue_info_label = ttk.Label(hdr, text="0 items", font=("Segoe UI", 8, "bold"))
        self.queue_info_label.pack(side=LEFT)

        self.remove_btn = ttk.Button(hdr, text="🗑️ Remove",
                                     command=self._remove_selected,
                                     style=self._bs("warning"))
        self.remove_btn.pack(side=RIGHT)

        tc = ttk.Frame(frame)
        tc.pack(fill=BOTH, expand=YES)
        tc.rowconfigure(0, weight=1)
        tc.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(tc,
                                 columns=("source", "destination", "size", "status"),
                                 show="headings", height=5)
        for col, text, w, anc in [
            ("source", "Source", 195, W),
            ("destination", "Destination", 195, W),
            ("size", "Size", 65, CENTER),
            ("status", "Status", 85, CENTER),
        ]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, minwidth=w, anchor=anc)

        sb = ttk.Scrollbar(tc, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky=NSEW)
        sb.grid(row=0, column=1, sticky=NS)

        self.tree.tag_configure("Pending", foreground="#6c757d")
        self.tree.tag_configure("Moving", foreground="#0d6efd", font=("Segoe UI", 8, "bold"))
        self.tree.tag_configure("Success", foreground="#198754", font=("Segoe UI", 8, "bold"))
        self.tree.tag_configure("Error", foreground="#dc3545", font=("Segoe UI", 8, "bold"))
        self.tree.tag_configure("Skipped", foreground="#fd7e14", font=("Segoe UI", 8, "bold"))

    def _create_control_section(self, parent):
        frame = ttk.Labelframe(parent, text="⚡ Controls", style=self._cs())
        frame.grid(row=4, column=0, sticky=EW, pady=(0, 4))
        frame.columnconfigure(0, weight=1)

        of = ttk.Frame(frame)
        of.pack(fill=X, pady=(0, 4))
        of.columnconfigure(1, weight=1)
        ttk.Label(of, text="Overall:", font=("Segoe UI", 7)).grid(row=0, column=0, sticky=W, padx=(0, 6))
        self.overall_bar = ttk.Progressbar(of, orient=HORIZONTAL, mode="determinate")
        self.overall_bar.grid(row=0, column=1, sticky=EW)
        self.overall_pct_label = ttk.Label(of, text="0/0", font=("Segoe UI", 7), width=6)
        self.overall_pct_label.grid(row=0, column=2, sticky=E, padx=(6, 0))

        cf = ttk.Frame(frame)
        cf.pack(fill=X, pady=(0, 6))
        cf.columnconfigure(1, weight=1)
        ttk.Label(cf, text="Current:", font=("Segoe UI", 7)).grid(row=0, column=0, sticky=W, padx=(0, 6))
        self.item_bar = ttk.Progressbar(cf, orient=HORIZONTAL, mode="determinate", maximum=100)
        self.item_bar.grid(row=0, column=1, sticky=EW)
        self.item_pct_label = ttk.Label(cf, text="0%", font=("Segoe UI", 7), width=6)
        self.item_pct_label.grid(row=0, column=2, sticky=E, padx=(6, 0))

        sf = ttk.Frame(frame)
        sf.pack(fill=X, pady=(0, 6))
        sf.columnconfigure(1, weight=1)

        self.progress_label = ttk.Label(sf, text="⏳ Ready", font=("Segoe UI", 8, "bold"))
        self.progress_label.grid(row=0, column=0, sticky=W)

        self.speed_label = ttk.Label(sf, text="", style="Speed.TLabel")
        self.speed_label.grid(row=0, column=1)

        self.time_label = ttk.Label(sf, text="", font=("Segoe UI", 7), foreground="#6c757d")
        self.time_label.grid(row=0, column=2, sticky=E)

        btnf = ttk.Frame(frame)
        btnf.pack()

        self.start_btn = ttk.Button(btnf, text="▶️ Start",
                                    style=self._bs("success"),
                                    command=self._start_moving_thread)
        self.start_btn.grid(row=0, column=0, padx=(0, 6))

        self.pause_btn = ttk.Button(btnf, text="⏸️ Pause",
                                    style=self._bs("warning"),
                                    command=self._toggle_pause, state=DISABLED)
        self.pause_btn.grid(row=0, column=1, padx=(0, 6))

        self.stop_btn = ttk.Button(btnf, text="⏹️ Stop",
                                   style=self._bs("danger"),
                                   command=self._stop_operation, state=DISABLED)
        self.stop_btn.grid(row=0, column=2)

        stf = ttk.Frame(frame)
        stf.pack(fill=X, pady=(6, 0))
        ttk.Separator(stf, orient=HORIZONTAL).pack(fill=X, pady=(0, 4))
        self.status_label = ttk.Label(stf, text="📱 Ready to transfer files",
                                      font=("Segoe UI", 7), foreground="#6c757d")
        self.status_label.pack(side=LEFT)

    def _build_restore_tab(self, parent):
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        info = ttk.Label(parent,
                         text="Restore moves the folder back to its original location and removes the symlink.",
                         font=("Segoe UI", 8), foreground="#6c757d", wraplength=640)
        info.grid(row=0, column=0, sticky=EW, padx=8, pady=(8, 4))

        tf = ttk.Labelframe(parent, text="📋 Transfer History", style=self._cs())
        tf.grid(row=1, column=0, sticky=NSEW, padx=8, pady=(0, 8))
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(0, weight=1)

        tc = ttk.Frame(tf)
        tc.pack(fill=BOTH, expand=YES)
        tc.rowconfigure(0, weight=1)
        tc.columnconfigure(0, weight=1)

        self.restore_tree = ttk.Treeview(tc,
                                         columns=("original", "current", "symlink", "date"),
                                         show="headings", height=10)
        for col, text, w, anc in [
            ("original", "Original Location", 190, W),
            ("current", "Current Location", 190, W),
            ("symlink", "Symlink", 70, CENTER),
            ("date", "Moved On", 110, CENTER),
        ]:
            self.restore_tree.heading(col, text=text)
            self.restore_tree.column(col, width=w, minwidth=w, anchor=anc)

        rsb = ttk.Scrollbar(tc, orient=VERTICAL, command=self.restore_tree.yview)
        self.restore_tree.configure(yscrollcommand=rsb.set)
        self.restore_tree.grid(row=0, column=0, sticky=NSEW)
        rsb.grid(row=0, column=1, sticky=NS)

        self.restore_tree.tag_configure("ok", foreground="#198754")
        self.restore_tree.tag_configure("missing", foreground="#dc3545")
        self.restore_tree.tag_configure("no_symlink", foreground="#fd7e14")

        ctrl = ttk.Frame(parent)
        ctrl.grid(row=2, column=0, sticky=EW, padx=8, pady=(0, 8))
        ctrl.columnconfigure(0, weight=1)

        self.restore_status_label = ttk.Label(ctrl, text="",
                                              font=("Segoe UI", 7), foreground="#6c757d")
        self.restore_status_label.grid(row=0, column=0, sticky=W)

        btnf = ttk.Frame(ctrl)
        btnf.grid(row=0, column=1, sticky=E)

        ttk.Button(btnf, text="🔃 Refresh",
                   command=self._refresh_restore_tab,
                   style=self._bs()).pack(side=LEFT, padx=(0, 6))

        self.restore_btn = ttk.Button(btnf, text="🔄 Restore Selected",
                                      command=self._restore_selected,
                                      style=self._bs("danger"))
        self.restore_btn.pack(side=LEFT)

    def _on_tab_change(self, _event=None):
        if self.notebook.index("current") == 1:
            self._refresh_restore_tab()

    def _refresh_restore_tab(self):
        for iid in self.restore_tree.get_children():
            self.restore_tree.delete(iid)

        for rec in self.history.records:
            dest_exists = os.path.exists(rec["dest"])
            src_is_sym = is_symlink(rec["source"])
            sym_text = ("✅ Yes" if src_is_sym
                        else ("❌ No" if os.path.exists(rec["source"]) else "—"))

            if not dest_exists:
                tag = "missing"
            elif not src_is_sym:
                tag = "no_symlink"
            else:
                tag = "ok"

            try:
                ts = datetime.fromisoformat(rec["timestamp"]).strftime("%Y-%m-%d %H:%M")
            except Exception:
                ts = rec.get("timestamp", "")

            self.restore_tree.insert("", "end", iid=rec["dest"], values=(
                self._tail_truncate(rec["source"], 28),
                self._tail_truncate(rec["dest"], 28),
                sym_text, ts,
            ), tags=(tag,))

        n = len(self.history.records)
        self.restore_status_label.config(
            text=f"{n} record(s)  |  🟢 restorable  🟠 no symlink  🔴 dest missing"
        )

    def _restore_selected(self):
        selected = self.restore_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Select a record to restore.")
            return

        dest_path = selected[0]
        rec = next((r for r in self.history.records if r["dest"] == dest_path), None)
        if not rec:
            return

        source, dest = rec["source"], rec["dest"]

        if not os.path.exists(dest):
            messagebox.showerror("Restore Failed",
                                 f"File no longer at:\n{dest}")
            return

        msg = f"Restore '{os.path.basename(dest)}' back to:\n{source}\n\n"
        if is_symlink(source):
            msg += "• Symlink at original location will be removed\n"
        if os.path.exists(source) and not is_symlink(source):
            msg += f"⚠️ WARNING: '{source}' exists and is NOT a symlink — it will be overwritten!\n"
        msg += "\nContinue?"

        if not messagebox.askyesno("Confirm Restore", msg):
            return

        self.restore_btn.config(state=DISABLED)
        threading.Thread(target=self._do_restore, args=(rec,), daemon=True).start()

    def _do_restore(self, rec):
        source, dest = rec["source"], rec["dest"]
        try:
            if is_symlink(source):
                os.unlink(source)
            elif os.path.exists(source):
                shutil.rmtree(source) if os.path.isdir(source) else os.remove(source)

            mover = RobocopyMover(dest, source)
            mover.move()

            self.history.remove(dest)
            self.root.after(0, self._refresh_restore_tab)
            self.root.after(0, lambda: messagebox.showinfo(
                "Restore Complete",
                f"✅ '{os.path.basename(source)}' restored to:\n{source}"
            ))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Restore Failed", str(e)))
        finally:
            self.root.after(0, lambda: self.restore_btn.config(state=NORMAL))

    def _validate_paths(self, _event=None):
        source = self.source_var.get().strip()
        dest_root = self.dest_path_var.get().strip()
        self.add_btn.config(state=DISABLED)

        if self.is_moving:
            self._set_validation("⚠️ Transfer in progress", "#ffc107"); return
        if not dest_root:
            self._set_validation("💡 Set destination folder first", "#17a2b8"); return
        if not os.path.isdir(dest_root):
            self._set_validation("❌ Invalid destination folder", "#dc3545"); return
        if not source:
            self._set_validation("💡 Choose source folder to move", "#17a2b8"); return
        if not os.path.isdir(source):
            self._set_validation("❌ Source folder not found", "#dc3545"); return

        final_dest = os.path.join(dest_root, os.path.basename(source))
        if os.path.exists(final_dest):
            self._set_validation(f"❌ '{os.path.basename(source)}' already exists at destination", "#dc3545"); return

        with self.queue_lock:
            if any(it["source"] == os.path.normpath(source) for it in self.queue):
                self._set_validation("⚠️ Already in queue", "#ffc107"); return

        self._set_validation("✅ Ready to queue!", "#198754")
        self.add_btn.config(state=NORMAL)

    def _set_validation(self, text, color):
        self.validation_label.config(text=text, foreground=color)

    def _browse_dest(self):
        path = filedialog.askdirectory(title="Select Default Destination Folder")
        if path:
            self.dest_path_var.set(os.path.normpath(path))
            self._validate_paths()

    def _browse_source(self):
        path = filedialog.askdirectory(title="Select Source Folder",
                                       initialdir=self.settings.get("last_source_dir", str(Path.home())))
        if path:
            norm = os.path.normpath(path)
            self.source_var.set(norm)
            self.settings["last_source_dir"] = os.path.dirname(norm)
            self._validate_paths()

    def _add_to_queue(self):
        source = os.path.normpath(self.source_var.get().strip())
        dest = os.path.join(self.dest_path_var.get().strip(), os.path.basename(source))
        item = {"source": source, "dest": dest, "status": "Pending",
                "size": 0, "size_str": "...", "id": ""}
        with self.queue_lock:
            self.queue.append(item)
            idx = len(self.queue) - 1
        self._update_queue_display()
        self.source_var.set("")
        self._validate_paths()
        self._set_status(f"📥 Added: {os.path.basename(source)}")
        threading.Thread(target=self._calc_size_async, args=(idx,), daemon=True).start()

    def _calc_size_async(self, idx):
        with self.queue_lock:
            if idx >= len(self.queue):
                return
            source = self.queue[idx]["source"]
        size = self._get_folder_size(source)
        size_str = self._format_size(size)
        with self.queue_lock:
            if idx < len(self.queue):
                self.queue[idx]["size"] = size
                self.queue[idx]["size_str"] = size_str
        self.root.after(0, self._refresh_tree_row, idx)

    def _refresh_tree_row(self, idx):
        with self.queue_lock:
            if idx >= len(self.queue):
                return
            item = self.queue[idx]
        iid = item.get("id")
        if iid and self.tree.exists(iid):
            self.tree.set(iid, "size", item["size_str"])

    def _update_queue_display(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        with self.queue_lock:
            items_copy = list(self.queue)
        for i, item in enumerate(items_copy):
            disp, tag = self._status_display(item["status"])
            iid = self.tree.insert("", "end",
                                   values=(self._tail_truncate(item["source"], 26),
                                           self._tail_truncate(item["dest"], 26),
                                           item["size_str"], disp),
                                   tags=(tag,))
            with self.queue_lock:
                if i < len(self.queue):
                    self.queue[i]["id"] = iid
        with self.queue_lock:
            count = len(self.queue)
        self.queue_info_label.config(text=f"{count} items")

    def _status_display(self, status):
        return {
            "Pending": ("⏳ Pending", "Pending"),
            "Moving":  ("🔄 Moving",  "Moving"),
            "Success": ("✅ Done",    "Success"),
            "Error":   ("❌ Error",   "Error"),
            "Skipped": ("⏭️ Skip",    "Skipped"),
        }.get(status, (status, "Pending"))

    def _remove_selected(self):
        if self.is_moving:
            return
        selected = set(self.tree.selection())
        if not selected:
            return
        with self.queue_lock:
            self.queue = [it for it in self.queue if it["id"] not in selected]
        self._update_queue_display()
        self._set_status("🗑️ Removed from queue")

    def _set_item_status(self, idx, status):
        with self.queue_lock:
            if idx >= len(self.queue):
                return
            self.queue[idx]["status"] = status
            iid = self.queue[idx].get("id", "")
        disp, tag = self._status_display(status)
        def _upd():
            if iid and self.tree.exists(iid):
                self.tree.set(iid, "status", disp)
                self.tree.item(iid, tags=(tag,))
        self.root.after(0, _upd)

    def _start_moving_thread(self):
        if self.is_moving:
            return
        with self.queue_lock:
            pending = [i for i, it in enumerate(self.queue) if it["status"] == "Pending"]
        if not pending:
            return

        use_symlinks = is_admin()
        if not use_symlinks:
            if not messagebox.askyesno("Move Only Mode",
                                       "⚠️ Not running as Administrator.\n"
                                       "Symlinks will NOT be created.\nContinue?"):
                return

        if not messagebox.askyesno("Confirm Transfer", f"🚀 Transfer {len(pending)} item(s)?"):
            return

        self.is_moving = True
        self.operation_start_time = time.time()
        self.stop_event.clear()
        self.pause_event.set()
        self._toggle_controls(False)
        self.overall_bar.config(maximum=len(pending), value=0)
        self.overall_pct_label.config(text=f"0/{len(pending)}")

        threading.Thread(target=self._process_queue,
                         args=(use_symlinks, pending), daemon=True).start()

    def _process_queue(self, create_symlinks, pending_indices):
        total = len(pending_indices)
        success_count = error_count = skipped_count = 0

        for step, idx in enumerate(pending_indices):
            if self.stop_event.is_set():
                self._set_item_status(idx, "Skipped")
                skipped_count += 1
                continue

            self.pause_event.wait()

            if self.stop_event.is_set():
                self._set_item_status(idx, "Skipped")
                skipped_count += 1
                continue

            with self.queue_lock:
                item = self.queue[idx].copy()

            folder_name = os.path.basename(item["source"])
            self.current_operation = f"Moving {folder_name} ({step + 1}/{total})"
            self._set_item_status(idx, "Moving")
            self._item_percent = 0
            self._item_speed = ""
            self._item_eta = ""

            def progress_cb(percent, speed, eta, files):
                self._item_percent = percent
                self._item_speed = speed
                self._item_eta = eta

            mover = RobocopyMover(item["source"], item["dest"],
                                  progress_cb=progress_cb,
                                  stop_event=self.stop_event)
            move_ok = False
            try:
                mover.move()
                move_ok = True
            except Exception as e:
                self._set_item_status(idx, "Error")
                error_count += 1
                err_msg = str(e)
                self.root.after(0, lambda m=err_msg, n=folder_name:
                                messagebox.showerror("Move Failed",
                                                     f"Failed to move '{n}':\n{m}"))
                v = step + 1
                self.root.after(0, lambda v=v: (
                    self.overall_bar.config(value=v),
                    self.overall_pct_label.config(text=f"{v}/{total}")
                ))
                continue

            sym_created = False
            if move_ok and create_symlinks:
                try:
                    result = subprocess.run(
                        ["mklink", "/D", item["source"], item["dest"]],
                        shell=True, capture_output=True, text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    if result.returncode != 0:
                        raise RuntimeError(result.stderr.strip() or "mklink failed")
                    sym_created = True
                except Exception as e:
                    err_msg = str(e)
                    self.root.after(0, lambda m=err_msg, n=folder_name:
                                    messagebox.showwarning("Symlink Failed",
                                                           f"'{n}' moved OK but symlink failed:\n{m}"))

            self.history.add(item["source"], item["dest"], sym_created)
            self._set_item_status(idx, "Success")
            success_count += 1

            v = step + 1
            self.root.after(0, lambda v=v: (
                self.overall_bar.config(value=v),
                self.overall_pct_label.config(text=f"{v}/{total}")
            ))

        msg = f"🎉 Complete! ✅ {success_count} success, ❌ {error_count} failed"
        if skipped_count:
            msg += f", ⏭️ {skipped_count} skipped"
        self.root.after(0, lambda: self._finalize_operation(msg))

    def _toggle_pause(self):
        if not self.is_moving:
            return
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_event.clear()
            self.pause_btn.config(text="▶️ Resume")
        else:
            self.pause_event.set()
            self.pause_btn.config(text="⏸️ Pause")

    def _stop_operation(self):
        if self.is_moving and messagebox.askyesno(
            "Confirm Stop", "⚠️ Stop? Current item will finish copying first."
        ):
            self.stop_event.set()
            if self.is_paused:
                self.pause_event.set()

    def _finalize_operation(self, message):
        self.is_moving = False
        self.is_paused = False
        self.current_operation = ""
        self._item_percent = 0
        self._item_speed = ""
        self._item_eta = ""
        self.item_bar["value"] = 0
        self.item_pct_label.config(text="0%")
        self.pause_btn.config(text="⏸️ Pause")
        self._toggle_controls(True)
        self._set_status(message)
        messagebox.showinfo("Operation Finished", message)

    def _toggle_controls(self, enabled):
        state = NORMAL if enabled else DISABLED
        for w in [self.source_browse_btn, self.add_btn, self.start_btn, self.remove_btn]:
            w.config(state=state)
        self.pause_btn.config(state=DISABLED if enabled else NORMAL)
        self.stop_btn.config(state=DISABLED if enabled else NORMAL)
        if enabled:
            self._validate_paths()

    def _set_status(self, msg):
        self.root.after(0, lambda: self.status_label.config(text=msg))

    def _update_status_loop(self):
        if self.is_moving:
            if self.is_paused:
                self.time_label.config(text="⏸️ Paused")
                self.progress_label.config(text="⏸️ Paused")
                self.speed_label.config(text="")
            else:
                elapsed = self._format_time(time.time() - self.operation_start_time)
                self.time_label.config(text=f"⏱️ {elapsed}")
                self.progress_label.config(text=f"🔄 {self.current_operation}")
                pct = self._item_percent
                self.item_bar["value"] = pct
                self.item_pct_label.config(text=f"{pct:.0f}%")
                parts = []
                if self._item_speed:
                    parts.append(self._item_speed)
                if self._item_eta:
                    parts.append(f"ETA {self._item_eta}")
                self.speed_label.config(text="  |  ".join(parts))
        else:
            self.time_label.config(text=datetime.now().strftime("%H:%M:%S"))
            self.progress_label.config(text="⏳ Ready")
            self.speed_label.config(text="")
            with self.queue_lock:
                pending = sum(1 for it in self.queue if it["status"] == "Pending")
            self.start_btn.config(
                text=f"▶️ Start ({pending})" if pending else "▶️ Start",
                state=NORMAL if pending else DISABLED
            )
        self.root.after(500, self._update_status_loop)

    def _create_context_menu(self):
        self.ctx_menu = tk.Menu(self.root, tearoff=0)
        self.ctx_menu.add_command(label="📂 Open Source",
                                  command=lambda: self._open_location("source"))
        self.ctx_menu.add_command(label="📁 Open Destination",
                                  command=lambda: self._open_location("dest"))
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="🗑️ Remove", command=self._remove_selected)
        self.tree.bind("<Button-3>", self._show_ctx_menu)

    def _show_ctx_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            if iid not in self.tree.selection():
                self.tree.selection_set(iid)
            self.ctx_menu.tk_popup(event.x_root, event.y_root)

    def _open_location(self, key):
        selected = self.tree.selection()
        if not selected:
            return
        iid = selected[0]
        with self.queue_lock:
            item = next((it for it in self.queue if it["id"] == iid), None)
        if not item:
            return
        path = item[key]
        if not os.path.exists(path):
            path = os.path.dirname(path)
        if os.path.exists(path):
            os.startfile(path)
        else:
            messagebox.showwarning("Not Found", f"Path does not exist:\n{path}")

    def _get_folder_size(self, path):
        total = 0
        try:
            for entry in os.scandir(path):
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False):
                        total += self._get_folder_size(entry.path)
                except (PermissionError, OSError):
                    pass
        except (PermissionError, OSError):
            pass
        return total

    def _format_size(self, b):
        if b == 0:
            return "0 B"
        units = ("B", "KB", "MB", "GB", "TB")
        i = 0
        while b >= 1024 and i < len(units) - 1:
            b /= 1024; i += 1
        return f"{b:.1f} {units[i]}"

    def _format_time(self, seconds):
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _tail_truncate(self, text, length):
        return text if len(text) <= length else "…" + text[-(length - 1):]

def main():
    try:
        if sys.platform == "win32":
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    root = bs.Window(themename="cosmo") if HAS_TTKBOOTSTRAP else tk.Tk()
    app = FolderMoverApp(root)

    try:
        root.geometry(app.settings.get("window_geometry", "720x640"))
    except Exception:
        root.geometry("720x640")

    root.mainloop()

if __name__ == "__main__":
    if sys.platform == "win32" and not is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable,
            " ".join(f'"{a}"' for a in sys.argv), None, 1
        )
    else:
        main()