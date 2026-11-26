#!/usr/bin/env python3
"""Interfaz grafica ligera (Tkinter) para FFmpeg en Linux y Windows."""

from collections import Counter
import json
import os
import re
import shlex
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk


CONFIG_PATH = os.path.expanduser("~/.config/ffmpeg-gui.json")
VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v")
VIDEO_FILETYPES = [
    ("Vídeos", "*.mp4 *.mkv *.webm *.mov *.avi *.m4v"),
    ("Todos los archivos", "*.*"),
]
MEDIA_FILETYPES = [
    ("Vídeo o Audio", "*.mp4 *.mkv *.webm *.mov *.mp3 *.m4a *.wav *.aac"),
    ("Todos los archivos", "*.*"),
]
TIME_RE = re.compile(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})")

THEMES = {
    "dark": {
        "bg": "#1e1e2e",
        "fg": "#e2e8f0",
        "panel": "#262637",
        "input_bg": "#141420",
        "input_fg": "#f8fafc",
        "btn_bg": "#334155",
        "btn_active": "#475569",
        "accent_bg": "#2563eb",
        "accent_active": "#1d4ed8",
        "accent_fg": "#ffffff",
        "danger_bg": "#dc2626",
        "danger_active": "#b91c1c",
        "select_bg": "#3b82f6",
        "border": "#3f3f56",
        "tab_bg": "#262637",
        "tab_active": "#334155",
    },
    "light": {
        "bg": "#f1f5f9",
        "fg": "#0f172a",
        "panel": "#e2e8f0",
        "input_bg": "#ffffff",
        "input_fg": "#0f172a",
        "btn_bg": "#cbd5e1",
        "btn_active": "#94a3b8",
        "accent_bg": "#2563eb",
        "accent_active": "#1d4ed8",
        "accent_fg": "#ffffff",
        "danger_bg": "#dc2626",
        "danger_active": "#b91c1c",
        "select_bg": "#2563eb",
        "border": "#cbd5e1",
        "tab_bg": "#e2e8f0",
        "tab_active": "#ffffff",
    },
}


def find_bin(name: str) -> str:
    """Busca ffmpeg/ffprobe priorizando /usr/bin en Linux para evitar wrappers firejail."""
    if os.name != "nt":
        sys_bin = f"/usr/bin/{name}"
        if os.path.isfile(sys_bin) and os.access(sys_bin, os.X_OK):
            return sys_bin
    return shutil.which(name) or ""


FFMPEG_BIN = find_bin("ffmpeg")
FFPROBE_BIN = find_bin("ffprobe")


def _select_all_entry(event: tk.Event) -> str:
    event.widget.selection_range(0, tk.END)
    event.widget.icursor(tk.END)
    return "break"


def _select_all_text(event: tk.Event) -> str:
    event.widget.tag_add(tk.SEL, "1.0", tk.END)
    event.widget.mark_set(tk.INSERT, "1.0")
    event.widget.see(tk.INSERT)
    return "break"


class _Tooltip:
    """Tooltip ligero con retardo y limite de apariciones por sesion."""

    def __init__(self, widget: tk.Widget, text: str, max_shows: int = 3, delay_ms: int = 400) -> None:
        self.widget = widget
        self.text = text
        self.max_shows = max_shows
        self.delay_ms = delay_ms
        self.shown_count = 0
        self.after_id: str | None = None
        self.tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event: tk.Event) -> None:
        if self.shown_count >= self.max_shows or not self.text:
            return
        self._cancel_timer()
        self.after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel_timer(self) -> None:
        if self.after_id is not None:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

    def _show(self) -> None:
        self.after_id = None
        if self.tip is not None or self.shown_count >= self.max_shows or not self.text:
            return
        self.shown_count += 1
        x = self.widget.winfo_rootx() + 14
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(
            self.tip,
            text=self.text,
            background="#0f172a",
            foreground="#f8fafc",
            relief=tk.SOLID,
            borderwidth=1,
            padx=8,
            pady=4,
            justify=tk.LEFT,
        )
        lbl.pack()

    def _hide(self, _event: tk.Event | None = None) -> None:
        self._cancel_timer()
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


def probe_video(path: str) -> dict:
    """Obtiene códec, resolución, FPS y estado de audio con ffprobe."""
    if not FFPROBE_BIN:
        raise RuntimeError("No se encontró 'ffprobe' en el sistema.")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    v_out = subprocess.check_output(
        [
            FFPROBE_BIN, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height,r_frame_rate",
            "-of", "csv=p=0", path,
        ],
        text=True,
        creationflags=flags,
    ).strip()
    parts = [p for p in v_out.split(",") if p]
    if len(parts) < 4:
        raise ValueError(f"No se encontró pista de vídeo válida en: {os.path.basename(path)}")
    codec, w, h, fps_raw = parts[:4]
    num, den = (fps_raw.split("/") + ["1"])[:2]
    fps = round(float(num) / float(den)) if float(den) else 30

    a_out = subprocess.check_output(
        [
            FFPROBE_BIN, "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name", "-of", "csv=p=0", path,
        ],
        text=True,
        creationflags=flags,
    ).strip()
    dur_out = subprocess.check_output(
        [FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        text=True,
        creationflags=flags,
    ).strip()
    try:
        duration = max(0.1, float(dur_out))
    except ValueError:
        duration = 1.0
    return {
        "codec": codec,
        "w": int(w),
        "h": int(h),
        "fps": fps,
        "duration": duration,
        "has_audio": bool(a_out),
        "audio_codec": a_out,
    }


def suffix_output(src: str, suffix: str, ext: str | None = None) -> str:
    """Genera ruta de salida automática junto al archivo origen."""
    base, orig_ext = os.path.splitext(src)
    return f"{base}{suffix}{ext or orig_ext}"


class FFmpegGUI:
    """Ventana principal de FFmpeg GUI."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("FFmpeg GUI")
        self.root.geometry("880x690")
        self.root.minsize(780, 600)

        self.process: subprocess.Popen | None = None
        self.is_busy = False
        self.temp_files: list[str] = []
        self.prefs = self._load_prefs()
        self.theme_name = self.prefs.get("theme", "dark")

        default_dir = os.path.expanduser("~/Vídeos")
        if not os.path.isdir(default_dir):
            default_dir = os.path.expanduser("~/Descargas")
        if not os.path.isdir(default_dir):
            default_dir = os.path.expanduser("~")
        self.last_output_dir = self.prefs.get("last_dir", default_dir)
        if not os.path.isdir(self.last_output_dir):
            self.last_output_dir = default_dir

        self.style = ttk.Style(self.root)
        self.style.theme_use("clam")

        self.root.bind_class("TEntry", "<Control-a>", _select_all_entry)
        self.root.bind_class("TEntry", "<Control-A>", _select_all_entry)
        self.root.bind_class("Text", "<Control-a>", _select_all_text)
        self.root.bind_class("Text", "<Control-A>", _select_all_text)
        self.root.bind("<Escape>", lambda _e: self._stop())

        self._context_target: tk.Widget | None = None
        self._build_context_menu()
        self._build_ui()
        self._apply_theme(self.theme_name)
        self._check_binary()
        self._refresh_join_list()
        self.run_btn.focus_set()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_context_menu(self) -> None:
        self.ctx_menu = tk.Menu(self.root, tearoff=0)
        self.ctx_menu.add_command(label="Cortar", command=lambda: self._ctx_event("<<Cut>>"))
        self.ctx_menu.add_command(label="Copiar", command=lambda: self._ctx_event("<<Copy>>"))
        self.ctx_menu.add_command(label="Pegar", command=lambda: self._ctx_event("<<Paste>>"))
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="Seleccionar todo", command=self._ctx_select_all)

        self.root.bind_class("TEntry", "<Button-3>", self._show_context_menu)
        self.root.bind_class("Text", "<Button-3>", self._show_context_menu)

    def _show_context_menu(self, event: tk.Event) -> None:
        self._context_target = event.widget
        self.ctx_menu.tk_popup(event.x_root, event.y_root)

    def _ctx_event(self, virtual_ev: str) -> None:
        if self._context_target is not None:
            self._context_target.focus_set()
            self._context_target.event_generate(virtual_ev)

    def _ctx_select_all(self) -> None:
        w = self._context_target
        if isinstance(w, tk.Text):
            w.tag_add(tk.SEL, "1.0", tk.END)
        elif isinstance(w, ttk.Entry):
            w.selection_range(0, tk.END)
            w.icursor(tk.END)

    def _load_prefs(self) -> dict:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_prefs(self) -> None:
        data = {"theme": self.theme_name, "last_dir": self.last_output_dir}
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _check_binary(self) -> None:
        if not FFMPEG_BIN or not shutil.which(FFMPEG_BIN):
            self._append_log(
                "[Aviso] No se encontró 'ffmpeg' en el sistema.\n"
                "Instálalo antes de procesar vídeos (ej. sudo apt install ffmpeg).\n\n"
            )

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill=tk.X, **pad)

        self.tab_join = ttk.Frame(self.notebook, padding=6)
        self.tab_trim = ttk.Frame(self.notebook, padding=6)
        self.tab_conv = ttk.Frame(self.notebook, padding=6)
        self.tab_trans = ttk.Frame(self.notebook, padding=6)
        self.tab_gif = ttk.Frame(self.notebook, padding=6)
        self.tab_help = ttk.Frame(self.notebook, padding=6)
        self.tab_credits = ttk.Frame(self.notebook, padding=6)

        self.notebook.add(self.tab_join, text="Unir carpeta")
        self.notebook.add(self.tab_trim, text="Cortar / Silenciar")
        self.notebook.add(self.tab_conv, text="Convertir / MP3")
        self.notebook.add(self.tab_trans, text="Rotar / Velocidad / Lado a lado")
        self.notebook.add(self.tab_gif, text="GIF / Captura")
        self.notebook.add(self.tab_help, text="Ayuda")
        self.notebook.add(self.tab_credits, text="Créditos")

        self._build_tab_join()
        self._build_tab_trim()
        self._build_tab_conv()
        self._build_tab_trans()
        self._build_tab_gif()
        self._build_help_tab(pad)
        self._build_credits_tab()

        # --- Botones de acción ---
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, **pad)

        self.run_btn = ttk.Button(btn_frame, text="Ejecutar", command=self._on_run, style="Accent.TButton")
        self.run_btn.pack(side=tk.LEFT)

        self.stop_btn = ttk.Button(
            btn_frame, text="Detener", command=self._stop, state=tk.DISABLED, style="Danger.TButton"
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(6, 0))
        _Tooltip(self.stop_btn, "Detiene la tarea actual (también puedes pulsar Esc).")

        btn_copy = ttk.Button(btn_frame, text="Copiar comando", command=self._copy_command)
        btn_copy.pack(side=tk.LEFT, padx=(6, 0))
        _Tooltip(btn_copy, "Copia el comando exacto de ffmpeg para usarlo en la terminal.")

        ttk.Button(btn_frame, text="Abrir carpeta", command=self._open_last_dir).pack(side=tk.LEFT, padx=(6, 0))

        self.theme_btn = ttk.Button(btn_frame, text="Modo claro", command=self._toggle_theme)
        self.theme_btn.pack(side=tk.RIGHT, padx=(6, 0))

        ttk.Button(btn_frame, text="Limpiar salida", command=self._clear_log).pack(side=tk.RIGHT, padx=(6, 0))
        btn_copy_log = ttk.Button(btn_frame, text="Copiar salida", command=self._copy_log)
        btn_copy_log.pack(side=tk.RIGHT)
        _Tooltip(btn_copy_log, "Copia todo el texto de la consola 'Salida en vivo' al portapapeles.")

        # --- Consola en vivo ---
        log_frame = ttk.LabelFrame(main, text="Salida en vivo", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=True, **pad)

        self.log = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=11, state=tk.DISABLED, font=("TkFixedFont", 9))
        self.log.pack(fill=tk.BOTH, expand=True)

        # --- Barra de estado ---
        status_frame = ttk.Frame(main)
        status_frame.pack(fill=tk.X, padx=8, pady=(2, 0))
        self.status_var = tk.StringVar(value="Estado: Listo")
        self.progress_var = tk.StringVar(value="Progreso: --:--:--")
        ttk.Label(status_frame, textvariable=self.status_var).pack(side=tk.LEFT)
        ttk.Label(status_frame, textvariable=self.progress_var).pack(side=tk.RIGHT)

    def _add_path_row(self, parent: ttk.Frame, row: int, label: str, var: tk.StringVar, mode: str, filetypes=None, on_pick=None) -> tuple[ttk.Entry, ttk.Button]:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=4, padx=(0, 8))
        entry = ttk.Entry(parent, textvariable=var, width=54)
        entry.grid(row=row, column=1, sticky=tk.EW, pady=4)
        parent.columnconfigure(1, weight=1)

        def browse() -> None:
            if mode == "dir":
                val = filedialog.askdirectory(initialdir=var.get() or self.last_output_dir)
            elif mode == "save":
                val = filedialog.asksaveasfilename(initialdir=self.last_output_dir, initialfile=os.path.basename(var.get()))
            else:
                val = filedialog.askopenfilename(initialdir=self.last_output_dir, filetypes=filetypes or VIDEO_FILETYPES)
            if val:
                var.set(val)
                self.last_output_dir = val if os.path.isdir(val) else os.path.dirname(val)
                if on_pick:
                    on_pick(val)

        btn = ttk.Button(parent, text="Examinar...", command=browse)
        btn.grid(row=row, column=2, padx=(6, 0), pady=4)
        return entry, btn

    def _build_tab_join(self) -> None:
        self.join_dir = tk.StringVar(value=self.last_output_dir)
        self.join_no_audio = tk.BooleanVar(value=False)
        self.join_out = tk.StringVar(value="unido.mp4")
        self.join_res = tk.StringVar(value="Auto (mayoría)")
        self.join_fps = tk.StringVar(value="Auto (mayoría)")
        self.join_crf = tk.StringVar(value="Auto / Equilibrada (CRF 23)")

        cfg_box = ttk.LabelFrame(self.tab_join, text="1. Carpeta de origen, salida y calidad", padding=8)
        cfg_box.pack(fill=tk.X, padx=4, pady=(0, 6))

        self._add_path_row(
            cfg_box, 0, "Carpeta de vídeos:", self.join_dir, "dir",
            on_pick=lambda _p: self._refresh_join_list(),
        )
        ttk.Label(cfg_box, text="Archivo de salida:").grid(row=1, column=0, sticky=tk.W, pady=4, padx=(0, 8))
        out_row = ttk.Frame(cfg_box)
        out_row.grid(row=1, column=1, columnspan=2, sticky=tk.EW, pady=4)
        e_out = ttk.Entry(out_row, textvariable=self.join_out, width=28)
        e_out.pack(side=tk.LEFT)
        _Tooltip(e_out, "Se guardará dentro de la carpeta seleccionada.")

        def update_name() -> None:
            cur = self.join_out.get().strip()
            if cur in ("unido.mp4", "unido_sin_audio.mp4", ""):
                self.join_out.set("unido_sin_audio.mp4" if self.join_no_audio.get() else "unido.mp4")

        chk = ttk.Checkbutton(out_row, text="Sin audio (silenciar todo)", variable=self.join_no_audio, command=update_name)
        chk.pack(side=tk.LEFT, padx=(14, 0))
        _Tooltip(chk, "Elimina todas las pistas de audio del vídeo final.")

        ttk.Label(cfg_box, text="Calidad / Res / FPS:").grid(row=2, column=0, sticky=tk.W, pady=4, padx=(0, 8))
        q_row = ttk.Frame(cfg_box)
        q_row.grid(row=2, column=1, columnspan=2, sticky=tk.W, pady=4)
        cb_crf = ttk.Combobox(q_row, textvariable=self.join_crf, state="readonly", width=26, values=["Auto / Equilibrada (CRF 23)", "Alta (CRF 20)", "Ligera (CRF 27)"])
        cb_crf.pack(side=tk.LEFT)
        _Tooltip(cb_crf, "En 'Auto', si los vídeos son iguales copia directo; si recodifica usa CRF 23.")
        cb_res = ttk.Combobox(q_row, textvariable=self.join_res, state="readonly", width=15, values=["Auto (mayoría)", "1080p", "720p", "480p"])
        cb_res.pack(side=tk.LEFT, padx=8)
        _Tooltip(cb_res, "Fuerza resolución de salida respetando orientación (vertical u horizontal).")
        cb_fps = ttk.Combobox(q_row, textvariable=self.join_fps, state="readonly", width=15, values=["Auto (mayoría)", "24", "30", "60"])
        cb_fps.pack(side=tk.LEFT)
        _Tooltip(cb_fps, "Fuerza los fotogramas por segundo del vídeo unido.")

        list_box = ttk.LabelFrame(self.tab_join, text="2. Vídeos que se unirán (en orden alfabético)", padding=6)
        list_box.pack(fill=tk.BOTH, expand=True, padx=4)

        top_bar = ttk.Frame(list_box)
        top_bar.pack(fill=tk.X, pady=(0, 4))
        self.join_count_var = tk.StringVar(value="Detectados: 0 vídeos")
        ttk.Label(top_bar, textvariable=self.join_count_var).pack(side=tk.LEFT)
        ttk.Button(top_bar, text="Actualizar lista", command=self._refresh_join_list).pack(side=tk.RIGHT)

        list_wrap = ttk.Frame(list_box)
        list_wrap.pack(fill=tk.BOTH, expand=True)
        self.join_listbox = tk.Listbox(list_wrap, height=5, activestyle="none", borderwidth=1, relief=tk.FLAT)
        sb = ttk.Scrollbar(list_wrap, orient=tk.VERTICAL, command=self.join_listbox.yview)
        self.join_listbox.configure(yscrollcommand=sb.set)
        self.join_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

    @staticmethod
    def _list_join_videos(carpeta: str, out_name: str) -> list[str]:
        return sorted(
            os.path.join(carpeta, f)
            for f in os.listdir(carpeta)
            if f.lower().endswith(VIDEO_EXTS) and f not in (out_name, "unido.mp4", "unido_sin_audio.mp4")
        )

    def _refresh_join_list(self) -> None:
        self.join_listbox.delete(0, tk.END)
        carpeta = self.join_dir.get().strip()
        out_name = self.join_out.get().strip()
        if not os.path.isdir(carpeta):
            self.join_count_var.set("Carpeta no válida")
            return
        files = self._list_join_videos(carpeta, out_name)
        for idx, path in enumerate(files, 1):
            self.join_listbox.insert(tk.END, f"{idx:02d}. {os.path.basename(path)}")
        if not files:
            self.join_listbox.insert(tk.END, "(Sin vídeos detectados. Elige una carpeta con .mp4/.mkv/.webm/.mov/.avi)")
        self.join_count_var.set(f"Detectados: {len(files)} vídeos (copia directa si son iguales, o normalización automática si difieren)")

    def _build_tab_trim(self) -> None:
        self.trim_in = tk.StringVar()
        self.trim_out = tk.StringVar()
        self.trim_start = tk.StringVar(value="00:00:00")
        self.trim_end = tk.StringVar(value="00:00:30")
        self.trim_mode = tk.StringVar(value="Rápido (sin recodificar)")
        self.trim_no_audio = tk.BooleanVar(value=False)

        files_box = ttk.LabelFrame(self.tab_trim, text="1. Archivos", padding=8)
        files_box.pack(fill=tk.X, padx=4, pady=(0, 6))
        self._add_path_row(files_box, 0, "Vídeo entrada:", self.trim_in, "file", on_pick=lambda p: self.trim_out.set(suffix_output(p, "_recorte")))
        self._add_path_row(files_box, 1, "Vídeo salida:", self.trim_out, "save")

        opts_box = ttk.LabelFrame(self.tab_trim, text="2. Rango de corte y audio", padding=8)
        opts_box.pack(fill=tk.X, padx=4)

        times = ttk.Frame(opts_box)
        times.grid(row=0, column=1, sticky=tk.W, pady=4)
        ttk.Label(opts_box, text="Tiempo (Inicio / Fin):").grid(row=0, column=0, sticky=tk.W, pady=4, padx=(0, 8))
        e_start = ttk.Entry(times, textvariable=self.trim_start, width=10)
        e_start.pack(side=tk.LEFT)
        _Tooltip(e_start, "Formato HH:MM:SS o segundos (ej. 00:01:15 o 75).")
        ttk.Label(times, text="  →  ").pack(side=tk.LEFT)
        e_end = ttk.Entry(times, textvariable=self.trim_end, width=10)
        e_end.pack(side=tk.LEFT)
        cb_mode = ttk.Combobox(times, textvariable=self.trim_mode, state="readonly", width=24, values=["Rápido (sin recodificar)", "Exacto (recodificar)"])
        cb_mode.pack(side=tk.LEFT, padx=(10, 0))
        _Tooltip(cb_mode, "Rápido tarda segundos sin perder calidad; Exacto corta al fotograma preciso.")

        opts = ttk.Frame(opts_box)
        opts.grid(row=1, column=1, sticky=tk.W, pady=4)
        ttk.Checkbutton(opts, text="Quitar audio al recortar", variable=self.trim_no_audio).pack(side=tk.LEFT)
        self.mute_btn = ttk.Button(opts, text="Solo silenciar vídeo completo (1 clic)", command=self._quick_mute)
        self.mute_btn.pack(side=tk.LEFT, padx=(14, 0))
        _Tooltip(self.mute_btn, "Quita el audio del vídeo entero al instante sin recodificar.")

    def _build_tab_conv(self) -> None:
        self.conv_in = tk.StringVar()
        self.conv_out = tk.StringVar()
        self.conv_fmt = tk.StringVar(value="MP4 (H.264)")
        self.conv_res = tk.StringVar(value="Original")
        self.conv_crf = tk.StringVar(value="Equilibrada (CRF 23)")

        def update_conv_out(*_args) -> None:
            fmt = self.conv_fmt.get()
            is_mp3 = "MP3" in fmt
            self.cb_conv_res.configure(state="disabled" if is_mp3 else "readonly")
            self.cb_conv_crf.configure(state="disabled" if is_mp3 else "readonly")
            src = self.conv_in.get().strip()
            if not src:
                return
            ext = ".mp3" if is_mp3 else (".mkv" if "MKV" in fmt else (".webm" if "WebM" in fmt else ".mp4"))
            self.conv_out.set(suffix_output(src, "_conv", ext))

        files_box = ttk.LabelFrame(self.tab_conv, text="1. Archivos", padding=8)
        files_box.pack(fill=tk.X, padx=4, pady=(0, 6))
        self._add_path_row(files_box, 0, "Vídeo entrada:", self.conv_in, "file", on_pick=lambda _p: update_conv_out())
        self._add_path_row(files_box, 1, "Archivo salida:", self.conv_out, "save")

        opts_box = ttk.LabelFrame(self.tab_conv, text="2. Formato, resolución y compresión", padding=8)
        opts_box.pack(fill=tk.X, padx=4)
        row = ttk.Frame(opts_box)
        row.grid(row=0, column=1, sticky=tk.W, pady=4)
        ttk.Label(opts_box, text="Ajustes de salida:").grid(row=0, column=0, sticky=tk.W, pady=4, padx=(0, 8))
        cb_fmt = ttk.Combobox(row, textvariable=self.conv_fmt, state="readonly", width=18, values=["MP4 (H.264)", "MKV (H.264)", "WebM (VP9)", "Solo Audio (MP3)"])
        cb_fmt.pack(side=tk.LEFT)
        cb_fmt.bind("<<ComboboxSelected>>", update_conv_out)
        self.cb_conv_res = ttk.Combobox(row, textvariable=self.conv_res, state="readonly", width=11, values=["Original", "1080p", "720p", "480p"])
        self.cb_conv_res.pack(side=tk.LEFT, padx=8)
        _Tooltip(self.cb_conv_res, "Escala la altura manteniendo la proporción original.")
        self.cb_conv_crf = ttk.Combobox(row, textvariable=self.conv_crf, state="readonly", width=20, values=["Alta (CRF 20)", "Equilibrada (CRF 23)", "Ligera (CRF 27)"])
        self.cb_conv_crf.pack(side=tk.LEFT)
        _Tooltip(self.cb_conv_crf, "CRF más bajo = más calidad y peso; CRF más alto = archivo más ligero.")

    def _build_tab_trans(self) -> None:
        self.trans_action = tk.StringVar(value="Rotar / Voltear")
        self.trans_in1 = tk.StringVar()
        self.trans_in2 = tk.StringVar()
        self.trans_out = tk.StringVar()
        self.trans_param = tk.StringVar(value="90° derecha")
        self.trans_keep_audio = tk.BooleanVar(value=True)

        op_box = ttk.LabelFrame(self.tab_trans, text="1. Operación", padding=8)
        op_box.pack(fill=tk.X, padx=4, pady=(0, 6))
        cb_op = ttk.Combobox(op_box, textvariable=self.trans_action, state="readonly", width=24, values=["Rotar / Voltear", "Cambiar velocidad", "Reemplazar audio", "2 vídeos lado a lado"])
        cb_op.pack(side=tk.LEFT)
        self.cb_param = ttk.Combobox(op_box, textvariable=self.trans_param, state="readonly", width=18, values=["90° derecha", "90° izquierda", "180°", "Espejo horizontal"])
        self.cb_param.pack(side=tk.LEFT, padx=8)
        self.chk_trans_audio = ttk.Checkbutton(op_box, text="Mantener audio", variable=self.trans_keep_audio)
        self.chk_trans_audio.pack(side=tk.LEFT)

        files_box = ttk.LabelFrame(self.tab_trans, text="2. Archivos", padding=8)
        files_box.pack(fill=tk.X, padx=4)
        self._add_path_row(files_box, 0, "Vídeo principal:", self.trans_in1, "file", on_pick=lambda p: self.trans_out.set(suffix_output(p, "_editado")))
        self.trans_in2_entry, self.trans_in2_btn = self._add_path_row(files_box, 1, "2.º vídeo / Audio:", self.trans_in2, "file", filetypes=MEDIA_FILETYPES)
        self._add_path_row(files_box, 2, "Archivo salida:", self.trans_out, "save")

        def on_op_change(_e=None) -> None:
            op = self.trans_action.get()
            needs_second = op in ("Reemplazar audio", "2 vídeos lado a lado")
            self.trans_in2_entry.configure(state="normal" if needs_second else "disabled")
            self.trans_in2_btn.configure(state="normal" if needs_second else "disabled")
            self.chk_trans_audio.configure(state="disabled" if op == "Reemplazar audio" else "normal")
            if op == "Rotar / Voltear":
                self.cb_param.configure(values=["90° derecha", "90° izquierda", "180°", "Espejo horizontal"], state="readonly")
                self.trans_param.set("90° derecha")
            elif op == "Cambiar velocidad":
                self.cb_param.configure(values=["0.5x (lenta)", "1.25x", "1.5x", "2x (rápida)"], state="readonly")
                self.trans_param.set("1.5x")
            else:
                self.cb_param.configure(values=[], state="disabled")
                self.trans_param.set("")

        cb_op.bind("<<ComboboxSelected>>", on_op_change)
        on_op_change()

    def _build_tab_gif(self) -> None:
        self.gif_mode = tk.StringVar(value="Crear GIF animado")
        self.gif_in = tk.StringVar()
        self.gif_out = tk.StringVar()
        self.gif_start = tk.StringVar(value="00:00:00")
        self.gif_dur = tk.StringVar(value="5")
        self.gif_width = tk.StringVar(value="480")

        files_box = ttk.LabelFrame(self.tab_gif, text="1. Modo y archivos", padding=8)
        files_box.pack(fill=tk.X, padx=4, pady=(0, 6))
        ttk.Label(files_box, text="Modo:").grid(row=0, column=0, sticky=tk.W, pady=4, padx=(0, 8))
        cb_mode = ttk.Combobox(files_box, textvariable=self.gif_mode, state="readonly", width=24, values=["Crear GIF animado", "Extraer foto (JPG)"])
        cb_mode.grid(row=0, column=1, sticky=tk.W, pady=4)
        self._add_path_row(files_box, 1, "Vídeo entrada:", self.gif_in, "file", on_pick=lambda _p: update_gif_out())
        self._add_path_row(files_box, 2, "Archivo salida:", self.gif_out, "save")

        opts_box = ttk.LabelFrame(self.tab_gif, text="2. Tiempo y tamaño", padding=8)
        opts_box.pack(fill=tk.X, padx=4)
        ttk.Label(opts_box, text="Segundo inicio:").grid(row=0, column=0, sticky=tk.W, pady=4, padx=(0, 8))
        row = ttk.Frame(opts_box)
        row.grid(row=0, column=1, sticky=tk.W, pady=4)
        ttk.Entry(row, textvariable=self.gif_start, width=10).pack(side=tk.LEFT)
        ttk.Label(row, text="  Duración (s): ").pack(side=tk.LEFT)
        self.gif_dur_entry = ttk.Entry(row, textvariable=self.gif_dur, width=5)
        self.gif_dur_entry.pack(side=tk.LEFT)
        ttk.Label(row, text="  Ancho (px): ").pack(side=tk.LEFT)
        self.gif_width_cb = ttk.Combobox(row, textvariable=self.gif_width, state="readonly", width=7, values=["320", "480", "640", "720"])
        self.gif_width_cb.pack(side=tk.LEFT)

        def update_gif_out(*_args) -> None:
            is_gif = "GIF" in self.gif_mode.get()
            self.gif_dur_entry.configure(state="normal" if is_gif else "disabled")
            self.gif_width_cb.configure(state="readonly" if is_gif else "disabled")
            src = self.gif_in.get().strip()
            if not src:
                return
            ext = ".gif" if is_gif else ".jpg"
            self.gif_out.set(suffix_output(src, "_clip" if is_gif else "_foto", ext))

        cb_mode.bind("<<ComboboxSelected>>", update_gif_out)

    def _build_help_tab(self, pad: dict) -> None:
        help_text = (
            "GUÍA RÁPIDA DE FFMPEG GUI\n"
            "====================================================================\n\n"
            "1. UNIR CARPETA\n"
            "   Une todos los vídeos de la carpeta en orden alfabético (01, 02...).\n"
            "   Si todos tienen el mismo formato/tamaño/FPS usa copia directa (segundos).\n"
            "   Si difieren, los adapta automáticamente a la resolución más común.\n\n"
            "2. CORTAR / SILENCIAR\n"
            "   • Rápido (sin recodificar): instantáneo, corta por keyframes cercanos.\n"
            "   • Exacto (recodificar): corta en el segundo exacto indicado.\n"
            "   • Botón 'Solo silenciar vídeo completo': quita el audio en 1 clic.\n\n"
            "3. CONVERTIR / MP3\n"
            "   • CRF 20 = máxima calidad | CRF 23 = equilibrada | CRF 27 = archivo ligero.\n"
            "   • 'Solo Audio (MP3)' extrae la pista de audio en MP3.\n\n"
            "4. ROTAR / VELOCIDAD / LADO A LADO\n"
            "   • 'Reemplazar audio': usa el campo '2.º vídeo / Audio' para elegir un .mp3.\n"
            "   • '2 vídeos lado a lado': junta vídeo principal (izq.) y segundo (der.).\n\n"
            "5. GIF / CAPTURA\n"
            "   • 'Crear GIF animado': genera un GIF con paleta optimizada.\n"
            "   • 'Extraer foto': guarda un fotograma exacto del segundo indicado.\n"
        )
        self.help_box = scrolledtext.ScrolledText(self.tab_help, wrap=tk.WORD, height=9)
        self.help_box.pack(fill=tk.BOTH, expand=True, **pad)
        self.help_box.insert("1.0", help_text)
        self.help_box.configure(state=tk.DISABLED)

    def _build_credits_tab(self) -> None:
        wrapper = ttk.Frame(self.tab_credits, padding=8)
        wrapper.pack(fill=tk.BOTH, expand=True)
        card = ttk.LabelFrame(wrapper, text="Acerca del proyecto", padding=12)
        card.pack(expand=True, fill=tk.BOTH)

        ttk.Label(card, text="FFmpeg GUI", font=("TkDefaultFont", 14, "bold")).pack(pady=(2, 2))
        ttk.Label(card, text="Interfaz gráfica ultraligera en Python + Tkinter para FFmpeg", font=("TkDefaultFont", 10, "italic")).pack(pady=(0, 8))
        ttk.Separator(card, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 10))

        info = ttk.Frame(card)
        info.pack()
        rows = [
            ("Autor:", "Kenny Waddell"),
            ("Licencia:", "GNU GPLv3 (Software Libre)"),
            ("Motor:", "FFmpeg (Python 3 + Tkinter)"),
            ("Repositorio:", "https://github.com/KennyWaddell/ffmpeg-gui"),
        ]
        for idx, (label, value) in enumerate(rows):
            ttk.Label(info, text=label, font=("TkDefaultFont", 10, "bold")).grid(row=idx, column=0, sticky=tk.E, padx=(0, 12), pady=2)
            ttk.Label(info, text=value).grid(row=idx, column=1, sticky=tk.W, pady=2)

        actions = ttk.Frame(card)
        actions.pack(pady=(12, 2))
        ttk.Button(
            actions,
            text="Copiar enlace de GitHub",
            command=lambda: self._copy_text("https://github.com/KennyWaddell/ffmpeg-gui", "Enlace de GitHub copiado al portapapeles"),
        ).pack(side=tk.LEFT)
        ttk.Button(actions, text="Comprobar versión de FFmpeg", command=self._check_version).pack(side=tk.LEFT, padx=(8, 0))

    def _apply_theme(self, name: str) -> None:
        self.theme_name = name if name in THEMES else "dark"
        t = THEMES[self.theme_name]
        self.root.configure(bg=t["bg"])

        self.style.configure(".", background=t["bg"], foreground=t["fg"], bordercolor=t["border"])
        self.style.configure("TFrame", background=t["bg"])
        self.style.configure("TNotebook", background=t["bg"], bordercolor=t["border"])
        self.style.configure("TNotebook.Tab", background=t["tab_bg"], foreground=t["fg"], padding=[10, 4])
        self.style.map("TNotebook.Tab", background=[("selected", t["tab_active"])], foreground=[("selected", t["fg"])])
        self.style.configure("TLabelframe", background=t["bg"], foreground=t["fg"])
        self.style.configure("TLabelframe.Label", background=t["bg"], foreground=t["fg"])
        self.style.configure("TLabel", background=t["bg"], foreground=t["fg"])
        self.style.configure("TCheckbutton", background=t["bg"], foreground=t["fg"])
        self.style.map("TCheckbutton", background=[("active", t["panel"])], foreground=[("active", t["fg"])])
        self.style.configure("TButton", background=t["btn_bg"], foreground=t["fg"], padding=5)
        self.style.map("TButton", background=[("active", t["btn_active"]), ("disabled", t["panel"])])
        self.style.configure("Accent.TButton", background=t["accent_bg"], foreground=t["accent_fg"], font=("TkDefaultFont", 10, "bold"), padding=(12, 5))
        self.style.map("Accent.TButton", background=[("active", t["accent_active"]), ("disabled", t["panel"])], foreground=[("disabled", t["fg"])])
        self.style.configure("Danger.TButton", background=t["danger_bg"], foreground=t["accent_fg"], font=("TkDefaultFont", 10, "bold"), padding=(10, 5))
        self.style.map("Danger.TButton", background=[("active", t["danger_active"]), ("disabled", t["panel"])], foreground=[("disabled", t["fg"])])
        self.style.configure("TEntry", fieldbackground=t["input_bg"], foreground=t["input_fg"], insertcolor=t["input_fg"])
        self.style.map("TEntry", fieldbackground=[("disabled", t["panel"])], foreground=[("disabled", t["border"])])
        self.style.configure("TCombobox", fieldbackground=t["input_bg"], background=t["btn_bg"], foreground=t["input_fg"])
        self.style.map("TCombobox", fieldbackground=[("readonly", t["input_bg"]), ("disabled", t["panel"])], foreground=[("readonly", t["input_fg"]), ("disabled", t["border"])], selectbackground=[("readonly", t["select_bg"])])

        self.log.configure(bg=t["input_bg"], fg=t["input_fg"], insertbackground=t["input_fg"], selectbackground=t["select_bg"])
        self.help_box.configure(bg=t["input_bg"], fg=t["input_fg"], selectbackground=t["select_bg"])
        self.join_listbox.configure(bg=t["input_bg"], fg=t["input_fg"], selectbackground=t["select_bg"], selectforeground=t["accent_fg"], highlightbackground=t["border"])
        self.theme_btn.configure(text="Modo claro" if self.theme_name == "dark" else "Modo oscuro")

    def _toggle_theme(self) -> None:
        self._apply_theme("light" if self.theme_name == "dark" else "dark")
        self._save_prefs()

    def _append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _clear_log(self) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)

    def _copy_log(self) -> None:
        text = self.log.get("1.0", tk.END).strip()
        if not text:
            self.status_var.set("Estado: La consola está vacía")
            return
        self._copy_text(text, "Salida en vivo copiada al portapapeles")

    def _open_last_dir(self) -> None:
        d = self.last_output_dir
        if os.name == "nt":
            os.startfile(d)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _set_busy(self, busy: bool) -> None:
        self.is_busy = busy
        self.run_btn.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self.mute_btn.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self.stop_btn.configure(state=tk.NORMAL if busy else tk.DISABLED)

    def _confirm_overwrite(self, out_path: str | None) -> bool:
        if out_path and os.path.exists(out_path):
            return messagebox.askyesno(
                "Archivo existente",
                f"El archivo ya existe:\n{out_path}\n\n¿Deseas sobrescribirlo?",
            )
        return True

    def _quick_mute(self) -> None:
        if self.is_busy:
            return
        src = self.trim_in.get().strip()
        if not src or not os.path.isfile(src):
            messagebox.showwarning("Falta archivo", "Selecciona primero un vídeo de entrada.")
            return
        out = suffix_output(src, "_sin_audio")
        if not self._confirm_overwrite(out):
            return
        self._launch_process([FFMPEG_BIN or "ffmpeg", "-y", "-i", src, "-c:v", "copy", "-an", out], out)

    def _build_current_command(self) -> tuple[list[str], str]:
        tab = self.notebook.index(self.notebook.select())
        if tab == 0:
            cmd, out, temp_list = self._cmd_join()
            if temp_list:
                self.temp_files.append(temp_list)
            return cmd, out
        if tab == 1:
            return self._cmd_trim()
        if tab == 2:
            return self._cmd_conv()
        if tab == 3:
            return self._cmd_trans()
        if tab == 4:
            return self._cmd_gif()
        raise ValueError("Selecciona una pestaña de operación (no Ayuda/Créditos).")

    def _copy_text(self, text: str, status_msg: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set(f"Estado: {status_msg}")

    def _copy_command(self) -> None:
        try:
            cmd, _ = self._build_current_command()
            self._cleanup_temps()
        except Exception as exc:
            messagebox.showwarning("Comando incompleto", str(exc))
            return
        self._copy_text(shlex.join(cmd), "Comando copiado al portapapeles")

    def _on_run(self) -> None:
        if self.is_busy:
            return
        tab = self.notebook.index(self.notebook.select())
        if tab == 0:
            self._start_join_async()
            return
        try:
            cmd, out = self._build_current_command()
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return
        if not self._confirm_overwrite(out):
            return
        self._launch_process(cmd, out)

    def _start_join_async(self) -> None:
        carpeta = self.join_dir.get().strip()
        if not os.path.isdir(carpeta):
            messagebox.showerror("Error", "Selecciona una carpeta válida.")
            return
        sin_audio = self.join_no_audio.get()
        out_name = self.join_out.get().strip() or ("unido_sin_audio.mp4" if sin_audio else "unido.mp4")
        out_path = os.path.join(carpeta, out_name)
        res_opt = self.join_res.get()
        fps_opt = self.join_fps.get()
        crf_opt = self.join_crf.get()

        files = self._list_join_videos(carpeta, out_name)
        if len(files) < 2:
            messagebox.showerror("Error", f"Se necesitan al menos 2 vídeos en {carpeta} (encontrados: {len(files)}).")
            return
        if not self._confirm_overwrite(out_path):
            return

        self._set_busy(True)
        self.status_var.set(f"Estado: Analizando {len(files)} vídeos...")
        self.progress_var.set("Progreso: --:--:--")

        def analyze_and_run() -> None:
            try:
                cmd, _, temp_list = self._cmd_join(
                    files=files, out_path=out_path, sin_audio=sin_audio, carpeta=carpeta,
                    out_name=out_name, res_opt=res_opt, fps_opt=fps_opt, crf_opt=crf_opt,
                )
                if temp_list:
                    self.root.after(0, self.temp_files.append, temp_list)
                self.root.after(0, self._launch_process, cmd, out_path)
            except Exception as exc:
                self.root.after(0, self._append_log, f"\n[Error al analizar vídeos: {exc}]\n\n")
                self.root.after(0, self.status_var.set, "Estado: Error")
                self.root.after(0, self._set_busy, False)

        threading.Thread(target=analyze_and_run, daemon=True).start()

    def _cmd_join(
        self,
        files: list[str] | None = None,
        out_path: str | None = None,
        sin_audio: bool | None = None,
        carpeta: str | None = None,
        out_name: str | None = None,
        res_opt: str | None = None,
        fps_opt: str | None = None,
        crf_opt: str | None = None,
    ) -> tuple[list[str], str, str | None]:
        carpeta = carpeta or self.join_dir.get().strip()
        if not os.path.isdir(carpeta):
            raise ValueError("Selecciona una carpeta válida.")
        sin_audio = self.join_no_audio.get() if sin_audio is None else sin_audio
        out_name = out_name or self.join_out.get().strip() or ("unido_sin_audio.mp4" if sin_audio else "unido.mp4")
        out_path = out_path or os.path.join(carpeta, out_name)
        res_opt = res_opt or self.join_res.get()
        fps_opt = fps_opt or self.join_fps.get()
        crf_opt = crf_opt or self.join_crf.get()

        if files is None:
            files = self._list_join_videos(carpeta, out_name)
        if len(files) < 2:
            raise ValueError(f"Se necesitan al menos 2 vídeos en {carpeta} (encontrados: {len(files)}).")

        infos = [probe_video(f) for f in files]
        target_w, target_h = Counter((i["w"], i["h"]) for i in infos).most_common(1)[0][0]
        target_fps = Counter(i["fps"] for i in infos).most_common(1)[0][0]
        force_reencode = ("Auto" not in res_opt) or ("Auto" not in fps_opt) or ("Auto" not in crf_opt)

        if "Auto" not in res_opt:
            short_side = int(res_opt[:-1])
            long_side = 1920 if short_side == 1080 else (1280 if short_side == 720 else 854)
            target_w, target_h = (short_side, long_side) if target_h > target_w else (long_side, short_side)
        if "Auto" not in fps_opt:
            target_fps = int(fps_opt)
        crf = "20" if "20" in crf_opt else ("27" if "27" in crf_opt else "23")

        same_video = len({(i["codec"], i["w"], i["h"], i["fps"]) for i in infos}) == 1
        same_audio = sin_audio or (all(i["has_audio"] for i in infos) and len({i["audio_codec"] for i in infos}) == 1)

        if not force_reencode and same_video and same_audio:
            list_file = os.path.join(carpeta, ".ffmpeg_gui_concat.txt")
            with open(list_file, "w", encoding="utf-8") as fh:
                for f in files:
                    fh.write("file '" + f.replace("'", "'\\''") + "'\n")
            cmd = [FFMPEG_BIN or "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c:v", "copy"]
            cmd += ["-an"] if sin_audio else ["-c:a", "copy"]
            cmd.append(out_path)
            return cmd, out_path, list_file

        inputs, filters, concat_inputs = [], [], []
        for idx, (f, info) in enumerate(zip(files, infos)):
            inputs += ["-i", f]
            filters.append(
                f"[{idx}:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={target_fps},format=yuv420p[v{idx}]"
            )
            if sin_audio:
                concat_inputs.append(f"[v{idx}]")
            else:
                if info["has_audio"]:
                    filters.append(f"[{idx}:a]aresample=44100:async=1,aformat=sample_fmts=fltp:channel_layouts=stereo[a{idx}]")
                else:
                    filters.append(f"anullsrc=r=44100:cl=stereo:d={info['duration']:.3f}[a{idx}]")
                concat_inputs.extend([f"[v{idx}]", f"[a{idx}]"])

        if sin_audio:
            filters.append("".join(concat_inputs) + f"concat=n={len(files)}:v=1:a=0[outv]")
            cmd = [FFMPEG_BIN or "ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[outv]", "-c:v", "libx264", "-preset", "veryfast", "-crf", crf, "-an", out_path]
        else:
            filters.append("".join(concat_inputs) + f"concat=n={len(files)}:v=1:a=1[outv][outa]")
            cmd = [FFMPEG_BIN or "ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[outv]", "-map", "[outa]", "-c:v", "libx264", "-preset", "veryfast", "-crf", crf, "-c:a", "aac", "-b:a", "128k", out_path]
        return cmd, out_path, None

    def _cmd_trim(self) -> tuple[list[str], str]:
        src = self.trim_in.get().strip()
        if not os.path.isfile(src):
            raise ValueError("Selecciona un vídeo de entrada válido.")
        start = self.trim_start.get().strip()
        end = self.trim_end.get().strip()
        if not start or not end:
            raise ValueError("Indica el tiempo de inicio y de fin.")
        s_sec = self._parse_seconds(start)
        e_sec = self._parse_seconds(end)
        if s_sec is not None and e_sec is not None and s_sec >= e_sec:
            raise ValueError("El tiempo de inicio debe ser menor que el tiempo de fin.")
        out = self.trim_out.get().strip() or suffix_output(src, "_recorte")
        cmd = [FFMPEG_BIN or "ffmpeg", "-y", "-ss", start, "-to", end, "-i", src]
        if "Rápido" in self.trim_mode.get():
            cmd += ["-c:v", "copy"]
            cmd += ["-an"] if self.trim_no_audio.get() else ["-c:a", "copy"]
        else:
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
            cmd += ["-an"] if self.trim_no_audio.get() else ["-c:a", "aac"]
        cmd.append(out)
        return cmd, out

    def _cmd_conv(self) -> tuple[list[str], str]:
        src = self.conv_in.get().strip()
        if not os.path.isfile(src):
            raise ValueError("Selecciona un vídeo de entrada válido.")
        fmt = self.conv_fmt.get()
        out = self.conv_out.get().strip()
        if "MP3" in fmt:
            out = out or suffix_output(src, "", ".mp3")
            return [FFMPEG_BIN or "ffmpeg", "-y", "-i", src, "-vn", "-c:a", "libmp3lame", "-q:a", "2", out], out

        crf = "20" if "20" in self.conv_crf.get() else ("27" if "27" in self.conv_crf.get() else "23")
        res = self.conv_res.get()
        vf = ["-vf", f"scale=-2:{res[:-1]}"] if res != "Original" else []
        if "WebM" in fmt:
            out = out or suffix_output(src, "_conv", ".webm")
            cmd = [FFMPEG_BIN or "ffmpeg", "-y", "-i", src, *vf, "-c:v", "libvpx-vp9", "-crf", crf, "-b:v", "0", "-c:a", "libopus", out]
        else:
            ext = ".mkv" if "MKV" in fmt else ".mp4"
            out = out or suffix_output(src, "_conv", ext)
            cmd = [FFMPEG_BIN or "ffmpeg", "-y", "-i", src, *vf, "-c:v", "libx264", "-preset", "fast", "-crf", crf, "-c:a", "aac", out]
        return cmd, out

    def _cmd_trans(self) -> tuple[list[str], str]:
        op = self.trans_action.get()
        src1 = self.trans_in1.get().strip()
        src2 = self.trans_in2.get().strip()
        if not os.path.isfile(src1):
            raise ValueError("Selecciona el vídeo principal.")
        out = self.trans_out.get().strip() or suffix_output(src1, "_editado")
        keep_audio = self.trans_keep_audio.get()

        if op == "Rotar / Voltear":
            mapping = {"90° derecha": "transpose=1", "90° izquierda": "transpose=2", "180°": "transpose=1,transpose=1", "Espejo horizontal": "hflip"}
            cmd = [FFMPEG_BIN or "ffmpeg", "-y", "-i", src1, "-vf", mapping[self.trans_param.get()], "-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
            cmd += ["-c:a", "copy"] if keep_audio else ["-an"]
            cmd.append(out)
        elif op == "Cambiar velocidad":
            spd = {"0.5x (lenta)": 0.5, "1.25x": 1.25, "1.5x": 1.5, "2x (rápida)": 2.0}[self.trans_param.get()]
            pts = f"setpts={1/spd:.4f}*PTS"
            if keep_audio and probe_video(src1)["has_audio"]:
                cmd = [FFMPEG_BIN or "ffmpeg", "-y", "-i", src1, "-filter_complex", f"[0:v]{pts}[v];[0:a]atempo={spd}[a]", "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", out]
            else:
                cmd = [FFMPEG_BIN or "ffmpeg", "-y", "-i", src1, "-vf", pts, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-an", out]
        elif op == "Reemplazar audio":
            if not os.path.isfile(src2):
                raise ValueError("Selecciona el archivo de audio en '2.º vídeo / Audio'.")
            cmd = [FFMPEG_BIN or "ffmpeg", "-y", "-i", src1, "-i", src2, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-shortest", out]
        else:
            if not os.path.isfile(src2):
                raise ValueError("Selecciona el segundo vídeo en '2.º vídeo / Audio'.")
            cmd = [FFMPEG_BIN or "ffmpeg", "-y", "-i", src1, "-i", src2, "-filter_complex", "[0:v]scale=-2:720,setsar=1,format=yuv420p[v0];[1:v]scale=-2:720,setsar=1,format=yuv420p[v1];[v0][v1]hstack=inputs=2[v]", "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
            cmd += ["-map", "0:a?", "-c:a", "aac"] if keep_audio else ["-an"]
            cmd.append(out)
        return cmd, out

    @staticmethod
    def _parse_seconds(val: str) -> float | None:
        try:
            parts = [float(p) for p in val.split(":")]
            if len(parts) == 1:
                return parts[0]
            if len(parts) == 2:
                return parts[0] * 60 + parts[1]
            if len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
        except ValueError:
            return None
        return None

    def _cmd_gif(self) -> tuple[list[str], str]:
        src = self.gif_in.get().strip()
        if not os.path.isfile(src):
            raise ValueError("Selecciona un vídeo de entrada válido.")
        start = self.gif_start.get().strip() or "00:00:00"
        if "GIF" in self.gif_mode.get():
            dur_raw = self.gif_dur.get().strip() or "5"
            try:
                if float(dur_raw) <= 0:
                    raise ValueError
            except ValueError:
                raise ValueError("La duración del GIF debe ser un número mayor que 0.")
            out = self.gif_out.get().strip() or suffix_output(src, "_clip", ".gif")
            w = self.gif_width.get().strip() or "480"
            vf = f"fps=12,scale={w}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
            return [FFMPEG_BIN or "ffmpeg", "-y", "-ss", start, "-t", dur_raw, "-i", src, "-vf", vf, out], out
        out = self.gif_out.get().strip() or suffix_output(src, "_foto", ".jpg")
        return [FFMPEG_BIN or "ffmpeg", "-y", "-ss", start, "-i", src, "-frames:v", "1", "-q:v", "2", out], out

    def _launch_process(self, cmd: list[str], out_path: str | None) -> None:
        if out_path:
            self.last_output_dir = os.path.dirname(os.path.abspath(out_path))
        self._save_prefs()
        self.progress_var.set("Progreso: --:--:--")
        self.status_var.set("Estado: Procesando...")
        self._append_log(f"$ {shlex.join(cmd)}\n\n")

        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        preexec = (lambda: os.nice(10)) if os.name != "nt" else None
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                errors="replace",
                creationflags=flags,
                preexec_fn=preexec,
            )
        except Exception as exc:
            self._append_log(f"\n[Error: {exc}]\n\n")
            self.status_var.set("Estado: Error")
            self._cleanup_temps()
            self._set_busy(False)
            return

        self._set_busy(True)
        threading.Thread(target=self._run_worker, args=(self.process, out_path), daemon=True).start()

    def _run_worker(self, proc: subprocess.Popen, out_path: str | None) -> None:
        try:
            assert proc.stdout is not None
            with proc.stdout:
                for line in proc.stdout:
                    self.root.after(0, self._append_log, line)
                    m = TIME_RE.search(line)
                    if m:
                        self.root.after(0, self.progress_var.set, f"Progreso: {m.group(1)}")
            code = proc.wait()
            if code == 0 and out_path:
                self.root.after(0, self._append_log, f"\n[Listo: {out_path}]\n\n")
            else:
                self.root.after(0, self._append_log, f"\n[Finalizado con código {code}]\n\n")
            self.root.after(0, self.status_var.set, f"Estado: Listo (código {code})")
        except Exception as exc:
            self.root.after(0, self._append_log, f"\n[Error: {exc}]\n\n")
            self.root.after(0, self.status_var.set, "Estado: Error")
        finally:
            self.root.after(0, self._on_finished)

    def _on_finished(self) -> None:
        self._cleanup_temps()
        self.process = None
        self._set_busy(False)
        self._refresh_join_list()

    def _terminate_process(self, proc: subprocess.Popen, force_wait: bool = False) -> None:
        try:
            proc.terminate()
        except OSError:
            return
        if force_wait:
            try:
                proc.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except OSError:
                    pass
        else:
            def _force_kill() -> None:
                if proc.poll() is None:
                    try:
                        proc.kill()
                    except OSError:
                        pass
            threading.Timer(2.0, _force_kill).start()

    def _stop(self) -> None:
        if self.process is not None and str(self.stop_btn["state"]) != tk.DISABLED:
            self.stop_btn.configure(state=tk.DISABLED)
            self._terminate_process(self.process, force_wait=False)
            self._append_log("\n[Deteniendo proceso...]\n")
            self.status_var.set("Estado: Deteniendo...")

    def _check_version(self) -> None:
        if self.is_busy:
            return
        self._launch_process([FFMPEG_BIN or "ffmpeg", "-version"], None)

    def _cleanup_temps(self) -> None:
        for p in self.temp_files:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        self.temp_files.clear()

    def _on_close(self) -> None:
        if self.process is not None:
            self._terminate_process(self.process, force_wait=True)
        self._cleanup_temps()
        self._save_prefs()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    FFmpegGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
