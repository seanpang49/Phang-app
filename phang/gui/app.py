"""
Phang GUI — tkinter desktop application.

Launch with:  phang gui
Or via the desktop shortcut: ~/Desktop/Phang.command
"""

from __future__ import annotations

import os

# Force matplotlib's headless Agg backend process-wide before anything can
# import matplotlib. The pipeline runs on a worker thread, where matplotlib's
# default Tk backend crashes/wedges off the main thread and blanks the GUI
# window (HANDOFF BUG #2). Setting MPLBACKEND before the first matplotlib import
# makes Agg win regardless of import order.
os.environ.setdefault("MPLBACKEND", "Agg")

import logging
import queue
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from typing import List, Optional

import tkinter as tk
from tkinter import filedialog, ttk, messagebox

from phang.config import FASTA_EXTENSIONS, VERSION

logger = logging.getLogger(__name__)

# ── Colour palette (matches report card dark theme) ────────────────────────
BG          = "#020617"
BG_CARD     = "#0f172a"
BG_INPUT    = "#1e293b"
BORDER      = "#334155"
TEXT        = "#e2e8f0"
TEXT_MUTED  = "#64748b"
TEXT_DIM    = "#475569"
ACCENT      = "#6366f1"
GREEN       = "#4ade80"
RED         = "#f87171"
AMBER       = "#fbbf24"
FONT_MONO   = ("Menlo", 11)
FONT_SANS   = ("SF Pro Text", 11) if sys.platform == "darwin" else ("Segoe UI", 11)
FONT_TITLE  = ("SF Pro Display", 18, "bold") if sys.platform == "darwin" else ("Segoe UI", 18, "bold")


# ── Logging handler that feeds into a Queue for the GUI ─────────────────────
class _QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue):
        super().__init__()
        self.q = q

    def emit(self, record: logging.LogRecord) -> None:
        self.q.put(("log", self.format(record)))


# ── Main application window ──────────────────────────────────────────────────
class PhangApp(tk.Tk):
    STEPS = [
        "Checking tools",
        "Pharokka — annotation",
        "Phold — structure re-annotation",
        "Phynteny — synteny annotation",
        "PhaStyle — lifestyle prediction",
        "PhaBOX2 — host prediction",
        "vConTACT3 — taxonomy",
        "DefenseFinder — antidefense systems",
        "RBPdetect — receptor-binding proteins",
        "DepoScope — depolymerases",
        "Genome visualisation",
        "NCBI BankIt package",
        "Generating report card",
    ]
    TOTAL_STEPS = len(STEPS)

    # Single-frame spinner cycled by the queue pollers to show the window is
    # alive during long silent stretches (a slow per-tool install or a multi-GB
    # database download can log nothing for minutes). ASCII so it renders in any
    # Tk font shipped with the packaged interpreter.
    _SPINNER = "|/-\\"

    _ICON_PATH = Path(__file__).parent / "assets" / "icon.png"

    def __init__(self):
        super().__init__()
        self.title(f"Phang  v{VERSION}")
        self.resizable(False, False)
        self.configure(bg=BG)
        self._set_icon()

        # State
        self._fasta_files: List[Path] = []
        self._output_dir: Optional[Path] = None
        self._mode = tk.StringVar(value="individual")
        self._running = False
        self._setup_running = False
        self._queue: queue.Queue = queue.Queue()
        self._current_step = 0
        self._result_paths: List[Path] = []
        # Latest status text each poller renders (with a spinner) so the window
        # keeps repainting even while the worker thread is silent under load.
        self._setup_status_base = ""
        self._run_status_base = ""
        self._spin = 0

        self._build_ui()
        self._center_window()

        # First launch only: install the 9 tool envs + download databases before
        # the pipeline can run. Deferred so the window paints first. Idempotent —
        # a completed bootstrap writes a manifest and this becomes a no-op.
        self.after(300, self._maybe_first_run_setup)

    # ── Icon ─────────────────────────────────────────────────────────────────

    def _set_icon(self) -> None:
        """Set window icon and taskbar icon."""
        try:
            icon = tk.PhotoImage(file=str(self._ICON_PATH))
            self.iconphoto(True, icon)
            self._icon_ref = icon  # prevent garbage collection
        except Exception:
            pass  # icon is cosmetic — ignore if it fails

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        pad = {"padx": 20, "pady": 0}

        # ── Header ──
        hdr = tk.Frame(self, bg=BG, pady=14)
        hdr.pack(fill="x")
        # Logo image
        try:
            logo_img = tk.PhotoImage(file=str(self._ICON_PATH))
            logo_img = logo_img.subsample(
                max(1, logo_img.width() // 52), max(1, logo_img.height() // 52)
            )
            logo_lbl = tk.Label(hdr, image=logo_img, bg=BG)
            logo_lbl.image = logo_img  # keep reference
            logo_lbl.pack(side="left", padx=(16, 8))
        except Exception:
            tk.Label(hdr, text="🦠", font=(*FONT_SANS[:1], 28),
                     bg=BG).pack(side="left", padx=(16, 8))
        tk.Label(hdr, text="Phang", font=FONT_TITLE,
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Label(hdr, text="  Phage Genome Analysis Pipeline",
                 font=(*FONT_SANS[:1], 12), bg=BG, fg=TEXT_MUTED).pack(side="left", padx=4)

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=0)

        # ── Main content ──
        content = tk.Frame(self, bg=BG, padx=20, pady=16)
        content.pack(fill="both")

        # Input files section
        self._build_section_label(content, "1  Input FASTA Files")
        self._drop_frame = self._build_drop_zone(content)
        self._file_list = self._build_file_list(content)
        self._build_file_buttons(content)

        self._vspace(content, 12)

        # Output folder
        self._build_section_label(content, "2  Output Folder")
        self._build_output_row(content)

        self._vspace(content, 12)

        # Mode
        self._build_section_label(content, "3  Report Mode")
        self._build_mode_row(content)

        self._vspace(content, 16)

        # Run button
        self._run_btn = tk.Button(
            content, text="▶  Run Pipeline",
            font=(*FONT_SANS[:1], 13, "bold"),
            bg=ACCENT, fg="white", relief="flat",
            activebackground="#4f46e5", activeforeground="white",
            cursor="hand2", pady=10,
            command=self._on_run,
        )
        self._run_btn.pack(fill="x")

        self._vspace(content, 14)

        # Progress area
        self._step_label = tk.Label(content, text="", font=FONT_MONO,
                                    bg=BG, fg=TEXT_MUTED, anchor="w")
        self._step_label.pack(fill="x")

        self._progress = ttk.Progressbar(content, length=460, mode="determinate",
                                         maximum=self.TOTAL_STEPS)
        self._progress.pack(fill="x", pady=(4, 0))

        self._pct_label = tk.Label(content, text="", font=(*FONT_MONO[:1], 10),
                                   bg=BG, fg=TEXT_DIM, anchor="e")
        self._pct_label.pack(fill="x")

        self._vspace(content, 8)

        # Status / done message
        self._status_label = tk.Label(content, text="", font=FONT_SANS,
                                      bg=BG, fg=TEXT, wraplength=460, justify="left")
        self._status_label.pack(fill="x")

        # Open results button (hidden until done)
        self._open_btn = tk.Button(
            content, text="📂  Open Results",
            font=(*FONT_SANS[:1], 12, "bold"),
            bg="#052e16", fg=GREEN, relief="flat",
            activebackground="#064e3b", activeforeground=GREEN,
            cursor="hand2", pady=8,
            command=self._on_open_results,
        )

        self._vspace(content, 4)

    def _build_section_label(self, parent: tk.Frame, text: str) -> None:
        tk.Label(parent, text=text,
                 font=(*FONT_SANS[:1], 10, "bold"),
                 bg=BG, fg=TEXT_MUTED).pack(anchor="w", pady=(0, 4))

    def _build_drop_zone(self, parent: tk.Frame) -> tk.Frame:
        frame = tk.Frame(parent, bg=BG_INPUT, relief="flat",
                         highlightbackground=BORDER, highlightthickness=1,
                         cursor="hand2")
        frame.pack(fill="x", pady=(0, 6))
        lbl = tk.Label(frame,
                       text="Drop FASTA files or a folder here\nor use the buttons below",
                       font=FONT_SANS, bg=BG_INPUT, fg=TEXT_MUTED, pady=18)
        lbl.pack()
        # Bind click to browse
        for w in (frame, lbl):
            w.bind("<Button-1>", lambda e: self._browse_files())
        # Try drag-and-drop
        try:
            from tkinterdnd2 import DND_FILES
            frame.drop_target_register(DND_FILES)
            frame.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass  # fallback: click-only
        return frame

    def _build_file_list(self, parent: tk.Frame) -> tk.Listbox:
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", pady=(0, 4))
        sb = tk.Scrollbar(frame, orient="vertical")
        lb = tk.Listbox(frame, height=4, font=FONT_MONO,
                        bg=BG_CARD, fg=TEXT, selectbackground=ACCENT,
                        relief="flat", highlightthickness=1,
                        highlightbackground=BORDER,
                        yscrollcommand=sb.set, activestyle="none")
        sb.config(command=lb.yview)
        sb.pack(side="right", fill="y")
        lb.pack(fill="x")
        return lb

    def _build_file_buttons(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x")
        # Primary: choose a whole folder (expanded recursively into FASTA files).
        tk.Button(row, text="Choose folder…", font=FONT_SANS,
                  bg=ACCENT, fg="white", relief="flat",
                  activebackground="#4f46e5", activeforeground="white",
                  cursor="hand2", padx=12, pady=4,
                  command=self._browse_folder).pack(side="left")
        tk.Button(row, text="Add files…", font=FONT_SANS,
                  bg=BG_INPUT, fg=TEXT, relief="flat",
                  activebackground=BORDER, cursor="hand2",
                  padx=12, pady=4,
                  command=self._browse_files).pack(side="left", padx=(6, 0))
        tk.Button(row, text="Clear", font=FONT_SANS,
                  bg=BG_INPUT, fg=TEXT_MUTED, relief="flat",
                  activebackground=BORDER, cursor="hand2",
                  padx=12, pady=4,
                  command=self._clear_files).pack(side="left", padx=(6, 0))

    def _build_output_row(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x")
        self._out_label = tk.Label(row, text="No folder selected",
                                   font=FONT_MONO, bg=BG_INPUT, fg=TEXT_MUTED,
                                   anchor="w", padx=10, pady=6,
                                   relief="flat",
                                   highlightbackground=BORDER, highlightthickness=1)
        self._out_label.pack(side="left", fill="x", expand=True)
        tk.Button(row, text="Choose…", font=FONT_SANS,
                  bg=BG_INPUT, fg=TEXT, relief="flat",
                  activebackground=BORDER, cursor="hand2",
                  padx=12, pady=6,
                  command=self._browse_output).pack(side="left", padx=(6, 0))

    def _build_mode_row(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x")
        for value, label in [("individual", "Individual report cards"),
                              ("batch", "Combined batch dashboard")]:
            rb = tk.Radiobutton(row, text=label, variable=self._mode,
                                value=value, font=FONT_SANS,
                                bg=BG, fg=TEXT, selectcolor=BG,
                                activebackground=BG, activeforeground=TEXT,
                                cursor="hand2")
            rb.pack(side="left", padx=(0, 20))

    def _vspace(self, parent: tk.Frame, h: int) -> None:
        tk.Frame(parent, bg=BG, height=h).pack()

    # ── Event handlers ───────────────────────────────────────────────────────

    def _on_drop(self, event) -> None:
        """Handle drag-and-drop of FASTA files and/or folders."""
        # tkinterdnd2 returns paths possibly wrapped in {} for paths with spaces
        paths = [Path(p) for p in self.tk.splitlist(event.data)]
        self._add_paths(paths)

    def _browse_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select FASTA files",
            filetypes=[("FASTA files", "*.fasta *.fa *.fna"), ("All files", "*.*")],
        )
        self._add_files([Path(p) for p in paths])

    def _browse_folder(self) -> None:
        """Pick a folder and expand it recursively into FASTA files."""
        d = filedialog.askdirectory(title="Choose a folder of FASTA files")
        if d:
            self._add_paths([Path(d)])

    def _clear_files(self) -> None:
        self._fasta_files.clear()
        self._file_list.delete(0, tk.END)

    def _browse_output(self) -> None:
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            self._output_dir = Path(d)
            self._out_label.config(text=str(self._output_dir), fg=TEXT)

    def _add_paths(self, paths: List[Path]) -> None:
        """Accept a mix of FASTA files and folders; expand folders recursively."""
        from phang.utils.fasta import find_fasta_files

        collected: List[Path] = []
        for p in paths:
            if p.is_dir():
                try:
                    collected.extend(find_fasta_files(p, recursive=True))
                except ValueError:
                    logger.warning("No FASTA files found in folder: %s", p)
            elif p.suffix.lower() in FASTA_EXTENSIONS:
                collected.append(p)
            else:
                logger.warning("Ignoring non-FASTA path: %s", p)

        if not collected:
            messagebox.showwarning(
                "No FASTA files",
                "No .fasta / .fa / .fna files were found in what you added.",
            )
            return
        self._add_files(collected)

    def _add_files(self, paths: List[Path]) -> None:
        for p in paths:
            if p not in self._fasta_files and p.is_file():
                self._fasta_files.append(p)
                self._file_list.insert(tk.END, f"  {p.name}")

    def _on_run(self) -> None:
        if self._running:
            return
        if self._setup_running:
            messagebox.showinfo(
                "Setup in progress",
                "Phang is still completing its one-time setup (installing tools and "
                "downloading databases). Please wait until setup finishes.",
            )
            return
        if not self._fasta_files:
            messagebox.showwarning("No files", "Please add at least one FASTA file.")
            return
        if self._output_dir is None:
            messagebox.showwarning("No output folder", "Please choose an output folder.")
            return

        self._running = True
        self._result_paths.clear()
        self._current_step = 0
        self._run_btn.config(state="disabled", text="Running…")
        self._open_btn.pack_forget()
        self._status_label.config(text="")
        self._progress["value"] = 0
        self._run_status_base = f"Step 0/{self.TOTAL_STEPS} — Starting…"
        self._step_label.config(text=self._run_status_base, fg=TEXT_MUTED)

        # Setup queue logging
        q = self._queue
        handler = _QueueHandler(q)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.setLevel(logging.INFO)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.DEBUG)

        # Run pipeline in background thread
        t = threading.Thread(
            target=self._run_pipeline_thread,
            args=(q, list(self._fasta_files), self._output_dir,
                  self._mode.get()),
            daemon=True,
        )
        t.start()

        # Start polling the queue
        self.after(100, self._poll_queue)

    def _run_pipeline_thread(self, q: queue.Queue, fasta_files: List[Path],
                              output_dir: Path, mode: str) -> None:
        """Run in a background thread — never touch tkinter widgets from here."""
        try:
            from phang.pipeline import run_pipeline
            from phang.utils.fasta import find_fasta_files

            # If multiple files, write them to a temp directory or use the first
            # For multiple files, create a temp input directory
            import tempfile, shutil

            if len(fasta_files) == 1:
                input_path = fasta_files[0]
            else:
                tmp_dir = Path(tempfile.mkdtemp(prefix="phang_input_"))
                for f in fasta_files:
                    shutil.copy2(f, tmp_dir / f.name)
                input_path = tmp_dir

            run_pipeline(
                input_path=input_path,
                output_path=output_dir,
                threads=8,
                gpu_mode="auto",
                force=False,
            )

            # Collect result paths
            result_paths = []
            if mode == "individual":
                result_paths = sorted(output_dir.glob("*/report_card.html"))
            else:
                # Generate batch dashboard
                from phang.gui.batch import build_batch_dashboard
                batch_html = build_batch_dashboard(output_dir)
                result_paths = [batch_html] if batch_html else sorted(output_dir.glob("*/report_card.html"))

            q.put(("done", result_paths))

        except Exception as exc:
            q.put(("error", str(exc)))

    def _flush(self) -> None:
        """Force pending widget repaints to the screen now. Used after terminal
        state changes so the final frame (e.g. "Setup complete") always paints,
        even when the main thread was being starved of redraw cycles."""
        try:
            self.update_idletasks()
        except tk.TclError:
            pass  # window closed

    def _heartbeat(self, base: str) -> None:
        """Re-render the active status line with a cycling spinner and flush the
        display. Keeps the window visibly alive and repainting even when the
        worker thread logs nothing for a while, or heavy (USB) disk I/O starves
        Tk's redraw cycle — the root cause of the first-run "frozen on a stale
        frame" symptom."""
        self._spin = (self._spin + 1) % len(self._SPINNER)
        if base:
            self._step_label.config(text=f"{self._SPINNER[self._spin]}  {base}")
        try:
            self.update_idletasks()
        except tk.TclError:
            pass  # window closed

    def _poll_queue(self) -> None:
        """Called by tkinter every 100ms to process messages from the pipeline thread."""
        try:
            while True:
                msg_type, data = self._queue.get_nowait()
                try:
                    if msg_type == "log":
                        self._handle_log(data)
                    elif msg_type == "done":
                        self._on_done(data)
                        return
                    elif msg_type == "error":
                        self._on_error(data)
                        return
                except Exception:
                    # A single malformed message must never kill the poll loop —
                    # that would freeze the UI mid-run with no recovery.
                    logger.exception("error handling pipeline message %r", msg_type)
        except queue.Empty:
            pass

        if self._running:
            self._heartbeat(self._run_status_base)
            self.after(100, self._poll_queue)

    def _handle_log(self, message: str) -> None:
        """Parse log messages to update progress bar and step label."""
        lower = message.lower()

        step_map = {
            "checking tool": 0,
            "[1/12]": 1,  "pharokka": 1,
            "[2/12]": 2,  "phold": 2,
            "[3/12]": 3,  "phynteny": 3,
            "[4/12]": 4,  "phastyle": 4,
            "[5/12]": 5,  "cherry": 5, "phabox2": 5,
            "[6/12]": 6,  "vcontact3": 6,
            "[7/12]": 7,  "defensefinder": 7,
            "[8/12]": 8,  "rbpdetect": 8,
            "[9/12]": 9,  "deposcope": 9,
            "[10/12]": 10, "genome viz": 10,
            "[11/12]": 11, "ncbi": 11,
            "[12/12]": 12, "report card": 12,
        }

        for key, step in step_map.items():
            if key in lower and step > self._current_step:
                self._current_step = step
                label = self.STEPS[step] if step < len(self.STEPS) else "Finishing…"
                # Store the base text; the heartbeat renders it (with a spinner)
                # and forces the repaint on the next poll tick.
                self._run_status_base = f"Step {step}/{self.TOTAL_STEPS} — {label}"
                self._step_label.config(fg=TEXT)
                self._progress["value"] = step
                pct = int(step / self.TOTAL_STEPS * 100)
                self._pct_label.config(text=f"{pct}%")
                break

    def _on_done(self, result_paths: List[Path]) -> None:
        self._running = False
        self._result_paths = result_paths
        self._progress["value"] = self.TOTAL_STEPS
        self._pct_label.config(text="100%")
        self._step_label.config(text=f"✅  Done! {len(result_paths)} report(s) ready.", fg=GREEN)
        self._run_btn.config(state="normal", text="▶  Run Pipeline")
        self._status_label.config(
            text=f"Results saved to:\n{self._output_dir}",
            fg=TEXT_MUTED,
        )
        self._open_btn.pack(fill="x", pady=(8, 0))
        self._flush()

    def _on_error(self, error: str) -> None:
        self._running = False
        self._run_btn.config(state="normal", text="▶  Run Pipeline")
        self._step_label.config(text="❌  Pipeline failed.", fg=RED)
        self._status_label.config(text=f"Error: {error}", fg=RED)
        self._flush()

    def _on_open_results(self) -> None:
        for path in self._result_paths:
            if path.exists():
                webbrowser.open(path.as_uri())

    # ── First-run setup (one-time bootstrap) ──────────────────────────────────

    _SETUP_TOOLS = [
        "pharokka", "phold", "phynteny", "phastyle", "phabox2",
        "defensefinder", "vcontact3", "rbpdetect", "deposcope",
    ]

    def _maybe_first_run_setup(self) -> None:
        """Run the one-time bootstrap on first launch (install tools + DBs).

        Skipped silently once a previous bootstrap has completed. If the install
        machinery can't be imported we simply continue — ``run_pipeline`` calls
        ``ensure_all`` itself, so the tools still get installed on first run.
        """
        try:
            from phang.install.bootstrap import is_bootstrapped
        except Exception:
            return
        if is_bootstrapped():
            return
        self._start_first_run_setup()

    def _start_first_run_setup(self) -> None:
        self._setup_running = True
        self._run_btn.config(state="disabled", text="Setting up…")
        self._status_label.config(
            text="First-time setup: installing the 9 analysis tools and downloading "
                 "their databases (~30 GB). This happens once and can take a while on "
                 "a fast connection. Keep this window open — quitting pauses setup and "
                 "it resumes next time (finished downloads are kept).",
            fg=AMBER,
        )
        self._setup_status_base = "Preparing setup…"
        self._step_label.config(text=self._setup_status_base, fg=TEXT_MUTED)
        self._progress.config(mode="determinate", maximum=len(self._SETUP_TOOLS))
        self._progress["value"] = 0
        self._pct_label.config(text="0%")

        # Stream the install logs into the GUI via the same queue the pipeline uses.
        handler = _QueueHandler(self._queue)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.setLevel(logging.INFO)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.DEBUG)
        self._setup_log_handler = handler

        threading.Thread(
            target=self._bootstrap_thread, args=(self._queue,), daemon=True
        ).start()
        self.after(100, self._poll_setup_queue)

    def _bootstrap_thread(self, q: queue.Queue) -> None:
        """Run in a background thread — never touch tkinter widgets from here."""
        try:
            from phang.install.bootstrap import bootstrap
            bootstrap()
            q.put(("setup_done", None))
        except BaseException as exc:  # SystemExit (fatal pharokka) included
            q.put(("setup_error", str(exc) or exc.__class__.__name__))

    def _poll_setup_queue(self) -> None:
        try:
            while True:
                msg_type, data = self._queue.get_nowait()
                try:
                    if msg_type == "log":
                        self._handle_setup_log(data)
                    elif msg_type == "setup_done":
                        self._on_setup_done()
                        return
                    elif msg_type == "setup_error":
                        self._on_setup_error(data)
                        return
                except Exception:
                    # One malformed log line must never kill the poll loop and
                    # leave setup looking frozen with no path to "complete".
                    logger.exception("error handling setup message %r", msg_type)
        except queue.Empty:
            pass
        if self._setup_running:
            self._heartbeat(self._setup_status_base)
            self.after(100, self._poll_setup_queue)

    def _handle_setup_log(self, message: str) -> None:
        text = message.strip()
        if text:
            # Store only; the heartbeat renders it (with a spinner) once per poll
            # tick rather than once per log line — far fewer Tcl calls under the
            # conda install's heavy log volume, and it forces a repaint.
            self._setup_status_base = text[:80]
        # The install manager logs "Checking tool: <name>" as each tool begins.
        low = message.lower()
        if "checking tool:" in low:
            name = low.split("checking tool:", 1)[1].strip()
            if name in self._SETUP_TOOLS:
                idx = self._SETUP_TOOLS.index(name) + 1
                self._progress["value"] = idx
                self._pct_label.config(
                    text=f"{int(idx / len(self._SETUP_TOOLS) * 100)}%"
                )

    def _finish_setup_logging(self) -> None:
        handler = getattr(self, "_setup_log_handler", None)
        if handler is not None:
            logging.getLogger().removeHandler(handler)
            self._setup_log_handler = None

    def _reset_progress_for_pipeline(self) -> None:
        self._progress.config(mode="determinate", maximum=self.TOTAL_STEPS)
        self._progress["value"] = 0
        self._pct_label.config(text="")

    def _on_setup_done(self) -> None:
        self._setup_running = False
        self._finish_setup_logging()
        self._progress["value"] = len(self._SETUP_TOOLS)
        self._pct_label.config(text="100%")
        self._step_label.config(
            text="✅  Setup complete — ready to analyse phages.", fg=GREEN
        )
        self._status_label.config(text="", fg=TEXT)
        self._run_btn.config(state="normal", text="▶  Run Pipeline")
        self._reset_progress_for_pipeline()
        self._flush()

    def _on_setup_error(self, error: str) -> None:
        self._setup_running = False
        self._finish_setup_logging()
        self._step_label.config(text="❌  Setup failed.", fg=RED)
        self._status_label.config(
            text=f"First-run setup failed: {error}\n\nQuit and reopen Phang to retry — "
                 f"finished downloads are kept. Full details are in "
                 f"~/Library/Logs/Phang/phang-gui.log.",
            fg=RED,
        )
        self._run_btn.config(state="normal", text="▶  Run Pipeline")
        self._reset_progress_for_pipeline()
        self._flush()

    # ── Utility ──────────────────────────────────────────────────────────────

    def _center_window(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2 - 40
        self.geometry(f"+{x}+{y}")


def launch() -> None:
    """Launch the Phang GUI. Entry point for `phang gui`."""
    # Decide whether drag-and-drop is actually usable *before* building the app.
    # tkinterdnd2 can import cleanly yet still fail to load its native tkdnd
    # library at TkinterDnD.Tk() construction — e.g. its bundled Apple-Silicon
    # build is libtcl9tkdnd2 (Tcl 9) while the packaged interpreter is Tcl/Tk
    # 8.6, which raises TclError "incompatible stubs mechanism". Probe on a
    # throwaway root so we fall back cleanly to plain tk.Tk (click-to-browse)
    # instead of crashing on launch.
    dnd_ok = False
    try:
        from tkinterdnd2 import TkinterDnD
        _probe = TkinterDnD.Tk()
        _probe.withdraw()        # never flash the throwaway probe window
        _probe.destroy()
        dnd_ok = True
    except Exception as e:
        logger.warning("Drag-and-drop unavailable (%s); using click-to-browse.", e)
        # TkinterDnD.Tk() builds the underlying Tk root *before* it loads the
        # native tkdnd library, so a load failure escapes with the root already
        # created — an orphaned empty "tk" window that also became the default
        # root. Tear it down so only the real app window remains.
        orphan = getattr(tk, "_default_root", None)
        if orphan is not None:
            try:
                orphan.destroy()
            except Exception:
                pass
            tk._default_root = None

    PhangApp.__bases__ = (TkinterDnD.Tk,) if dnd_ok else (tk.Tk,)
    app = PhangApp()
    app.mainloop()
