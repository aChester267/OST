#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pro Stress Test v9.1 (Fixed AMD Import)
---------------------------------------
• Исправлено падение программы на видеокартах NVIDIA, если установлена библиотека pyadl.
"""

import os
import sys
import time
import subprocess
import platform
import multiprocessing as mp
import threading
import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from collections import deque

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import moderngl
    import numpy as np
    import glfw
    HAS_GL = True
except ImportError:
    HAS_GL = False

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

try:
    import winsound
    HAS_SOUND = True
except ImportError:
    HAS_SOUND = False

# ИСПРАВЛЕНИЕ: Ловим любую ошибку, а не только ImportError
try:
    from pyadl import ADLManager
    HAS_ADL = True
except Exception:
    HAS_ADL = False

# --- Глобальные переменные ---
SMI_PATH = None
GPU_VENDOR = "UNKNOWN"  # "NVIDIA", "AMD", "INTEL", "UNKNOWN"
MONITOR_DATA = {"load": "—", "temp": "—"}
STOP_MONITOR_THREAD = False

# ============================================================
# ОПРЕДЕЛЕНИЕ ВЕНДОРА GPU И МОНИТОРИНГ
# ============================================================
def detect_gpu_vendor():
    global GPU_VENDOR, SMI_PATH
    
    # 1. Проверяем NVIDIA
    try:
        subprocess.check_output(["nvidia-smi"], creationflags=subprocess.CREATE_NO_WINDOW)
        SMI_PATH = "nvidia-smi"
        GPU_VENDOR = "NVIDIA"
        return "NVIDIA"
    except Exception:
        pass
    
    paths = [
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        r"C:\Windows\System32\nvidia-smi.exe"
    ]
    for p in paths:
        if os.path.exists(p):
            SMI_PATH = p
            GPU_VENDOR = "NVIDIA"
            return "NVIDIA"

    # 2. Проверяем AMD
    if HAS_ADL:
        try:
            manager = ADLManager.getInstance()
            devices = manager.getDevices()
            if devices:
                GPU_VENDOR = "AMD"
                return "AMD"
        except Exception:
            pass

    GPU_VENDOR = "UNKNOWN"
    return "UNKNOWN"

def get_gpu_name():
    if GPU_VENDOR == "NVIDIA" and SMI_PATH:
        try:
            out = subprocess.check_output(
                [SMI_PATH, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW
            ).strip()
            if out:
                parts = out.split(",")
                return parts[0].strip(), round(int(parts[1]) / 1024, 1)
        except Exception:
            pass
    elif GPU_VENDOR == "AMD" and HAS_ADL:
        try:
            manager = ADLManager.getInstance()
            devices = manager.getDevices()
            if devices:
                return devices[0].getName(), "N/A"
        except Exception:
            pass
    return "N/A", "N/A"

def monitor_thread_func():
    global MONITOR_DATA
    
    while not STOP_MONITOR_THREAD:
        try:
            if GPU_VENDOR == "NVIDIA" and SMI_PATH:
                out = subprocess.check_output(
                    [SMI_PATH, "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                    encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW, timeout=2
                ).strip()
                if out:
                    parts = out.split(",")
                    load_str = parts[0].strip()
                    MONITOR_DATA["load"] = "N/A" if "Not Supported" in load_str else f"{load_str}%"
                    MONITOR_DATA["temp"] = int(parts[1].strip())
            
            elif GPU_VENDOR == "AMD" and HAS_ADL:
                manager = ADLManager.getInstance()
                devices = manager.getDevices()
                if devices:
                    dev = devices[0]
                    try:
                        temp = dev.getCurrentTemperature()
                        load = dev.getCurrentUsage()
                        MONITOR_DATA["temp"] = int(temp) if temp is not None else "N/A"
                        MONITOR_DATA["load"] = f"{int(load)}%" if load is not None else "N/A"
                    except Exception:
                        pass

        except Exception:
            pass
        time.sleep(1.0)

# ============================================================
# CPU WORKER
# ============================================================
def get_cpu_name():
    try:
        if sys.platform == "win32":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        return platform.processor()
    except Exception: return "Unknown CPU"

def _timer_begin():
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)

def _timer_end():
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.winmm.timeEndPeriod(1)

def cpu_burner(stop_event, duty: float, worker_id: int):
    _timer_begin()
    mask = 0xFFFFFFFF
    x = 0xDEADBEEF ^ worker_id
    cycle = 0.1
    busy_time = cycle * duty

    while not stop_event.is_set():
        t0 = time.perf_counter()
        end_busy = t0 + busy_time
        while time.perf_counter() < end_busy:
            for _ in range(10000):
                x ^= (x << 13) & mask
                x ^= (x >> 17) & mask
                x ^= (x << 5) & mask
                x = (x * 1664525 + 1013904223) & mask
            if stop_event.is_set(): break
        elapsed = time.perf_counter() - t0
        sleep_time = cycle - elapsed
        if sleep_time > 0: time.sleep(sleep_time)
    _timer_end()

def gpu_burner(stop_event, duty: float, status_q):
    if not HAS_GL: return
    window = None
    try:
        if glfw.init():
            glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
            glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
            glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
            glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
            window = glfw.create_window(320, 240, "GL", None, None)
            if window:
                glfw.make_context_current(window)
                ctx = moderngl.create_context()
            else: return
        else: return
    except Exception: return

    renderer = ctx.info.get("GL_RENDERER", "unknown")
    is_intel = "intel" in renderer.lower() or "microsoft" in renderer.lower()
    status_q.put(("GL_RENDERER", renderer, not is_intel))

    vs = """#version 330 core\nin vec2 pos;\nvoid main() { gl_Position = vec4(pos, 0.0, 1.0); }"""
    fs = """
    #version 330 core
    uniform float u_time; uniform vec2 u_res; out vec4 frag_color;
    void main() {
        vec2 uv = (gl_FragCoord.xy - 0.5 * u_res) / u_res.y;
        vec3 ro = vec3(0.0, 0.0, -3.0); vec3 rd = normalize(vec3(uv, 1.0));
        float d = 0.0, acc = 0.0;
        for (int i = 0; i < 1024; i++) {
            vec3 p = ro + rd * d;
            float ds = length(p) - 1.0;
            ds += sin(p.x*10.0+u_time) * sin(p.y*10.0) * sin(p.z*10.0) * 0.1;
            d += max(ds, 0.01); acc += 0.002 / max(abs(ds), 0.01);
        }
        frag_color = vec4(sin(acc*2.0), cos(acc*1.5), sin(acc*0.5), 1.0);
    }"""
    
    try:
        res = (1920, 1080)
        tex = ctx.texture(res, 4)
        fbo = ctx.framebuffer(color_attachments=[tex])
        prog = ctx.program(vertex_shader=vs, fragment_shader=fs)
        verts = np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype="f4")
        vbo = ctx.buffer(verts.tobytes())
        vao = ctx.vertex_array(prog, [(vbo, "2f", "pos")])
        if "u_res" in prog: prog["u_res"].value = res

        t = 0.0
        while not stop_event.is_set():
            t0 = time.perf_counter()
            t += 0.016
            if "u_time" in prog: prog["u_time"].value = t
            fbo.use()
            vao.render(moderngl.TRIANGLE_STRIP)
            ctx.finish()
            render_time = time.perf_counter() - t0
            if duty < 0.99:
                sleep_time = (render_time / duty) - render_time
                if sleep_time > 0:
                    if stop_event.wait(sleep_time): break
    except Exception: pass
    finally:
        if window:
            try: glfw.destroy_window(window); glfw.terminate()
            except: pass

# ============================================================
# GUI
# ============================================================
class StressTestApp:
    TEMP_LIMIT = 90
    WARN_TEMP = 85

    def __init__(self, root: tk.Tk):
        global STOP_MONITOR_THREAD
        self.root = root
        self.mp_stop = mp.Event()
        self.status_q = mp.Queue()
        self.cpu_procs = []
        self.gpu_proc = None
        self.is_running = False
        self.time_left = 300
        self.timer_job = None

        self.cpu_name = get_cpu_name()
        self.gpu_vendor = detect_gpu_vendor()
        self.nv_name, self.nv_vram = get_gpu_name()
        
        self.load_target = tk.IntVar(value=100)
        self.time_target = tk.IntVar(value=300)
        self.gpu_status_var = tk.StringVar(value="Ожидание...")

        self.temp_history = deque(maxlen=60)
        self.max_temp = 0
        self.avg_temp_sum = 0
        self.avg_temp_count = 0

        self._setup_ui()
        
        STOP_MONITOR_THREAD = False
        self.mon_thread = threading.Thread(target=monitor_thread_func, daemon=True)
        self.mon_thread.start()
        self._update_monitor()

    def _setup_ui(self):
        self.root.title("Stress Test v9.1")
        self.root.geometry("620x850")
        self.root.configure(bg="#121212")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", background="#1e1e1e", foreground="#e0e0e0", font=("Segoe UI", 10))
        s.configure("Card.TFrame", background="#252525")
        s.configure("Info.TFrame", background="#1a1a1a")
        s.configure("Title.TLabel", foreground="#00e676", background="#1e1e1e", font=("Segoe UI", 16, "bold"))
        s.configure("Sub.TLabel", foreground="#888", background="#1e1e1e", font=("Segoe UI", 9))
        s.configure("Key.TLabel", foreground="#888", background="#1a1a1a", font=("Segoe UI", 9))
        s.configure("Val.TLabel", foreground="#e0e0e0", background="#1a1a1a", font=("Consolas", 9))
        s.configure("StatLabel.TLabel", foreground="#888", background="#252525", font=("Segoe UI", 9))
        s.configure("StatValue.TLabel", foreground="#00e676", background="#252525", font=("Consolas", 15, "bold"))
        s.configure("Timer.TLabel", foreground="#ffd600", background="#1e1e1e", font=("Consolas", 26, "bold"))
        s.configure("Start.TButton", background="#00e676", foreground="#000", font=("Segoe UI", 11, "bold"))
        s.map("Start.TButton", background=[("disabled", "#333")], foreground=[("disabled", "#666")])
        s.configure("Stop.TButton", background="#ff1744", foreground="#fff", font=("Segoe UI", 11, "bold"))
        s.map("Stop.TButton", background=[("disabled", "#333")], foreground=[("disabled", "#666")])
        s.configure("Load.TRadiobutton", background="#252525", foreground="#e0e0e0", font=("Segoe UI", 10, "bold"))
        s.configure("Action.TButton", background="#2196f3", foreground="#fff", font=("Segoe UI", 10, "bold"))
        s.map("Action.TButton", background=[("disabled", "#333")], foreground=[("disabled", "#666")])

        main = ttk.Frame(self.root, padding=15)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="PRO STRESS TEST v9.1", style="Title.TLabel").pack(anchor="w")
        ttk.Label(main, text=f"Поддержка: NVIDIA, AMD", style="Sub.TLabel").pack(anchor="w", pady=(0, 10))

        inf = ttk.Frame(main, style="Info.TFrame", padding=10)
        inf.pack(fill="x", pady=(0, 10))
        ic = f"{psutil.cpu_count(logical=False) if HAS_PSUTIL else '?'} физ / {os.cpu_count()} лог"
        
        vendor_text = f"{self.gpu_vendor}"
        if self.gpu_vendor == "AMD" and not HAS_ADL:
            vendor_text += " (pyadl не установлен)"

        for k, v in [
            ("CPU", self.cpu_name), ("Ядра", ic),
            ("GPU", f"{self.nv_name} ({vendor_text})" if self.nv_name != "N/A" else vendor_text)
        ]:
            r = ttk.Frame(inf, style="Info.TFrame")
            r.pack(fill="x", pady=1)
            ttk.Label(r, text=f"{k}:", width=12, style="Key.TLabel").pack(side="left")
            ttk.Label(r, text=str(v), style="Val.TLabel").pack(side="left")

        settings_frame = ttk.Frame(main, style="Card.TFrame", padding=10)
        settings_frame.pack(fill="x", pady=(0, 10))
        
        row1 = ttk.Frame(settings_frame, style="Card.TFrame")
        row1.pack(fill="x", pady=(0, 5))
        ttk.Label(row1, text="НАГРУЗКА:", style="StatLabel.TLabel").pack(side="left")
        for pct in (10, 25, 50, 75, 100):
            ttk.Radiobutton(row1, text=f"{pct}%", value=pct, variable=self.load_target, style="Load.TRadiobutton").pack(side="left", padx=5)

        row2 = ttk.Frame(settings_frame, style="Card.TFrame")
        row2.pack(fill="x")
        ttk.Label(row2, text="ВРЕМЯ:", style="StatLabel.TLabel").pack(side="left")
        for mins, sec in [("1 мин", 60), ("5 мин", 300), ("10 мин", 600), ("15 мин", 900)]:
            ttk.Radiobutton(row2, text=mins, value=sec, variable=self.time_target, style="Load.TRadiobutton").pack(side="left", padx=5)

        st = ttk.Frame(main)
        st.pack(fill="x", pady=(0, 10))
        for c in (0, 1, 2): st.columnconfigure(c, weight=1)
        
        self.cpu_load_var = tk.StringVar(value="—")
        self.gpu_load_var = tk.StringVar(value="—")
        self.gpu_temp_var = tk.StringVar(value="—")
        self.max_temp_var = tk.StringVar(value="0°C")
        self.workers_var = tk.StringVar(value="0")

        cards = [
            ("CPU LOAD", self.cpu_load_var), ("GPU LOAD", self.gpu_load_var),
            ("GPU TEMP", self.gpu_temp_var), ("MAX TEMP", self.max_temp_var),
            ("WORKERS", self.workers_var), ("STATUS", self.gpu_status_var)
        ]

        for i, (name, var) in enumerate(cards):
            card = ttk.Frame(st, style="Card.TFrame", padding=8)
            card.grid(row=i // 3, column=i % 3, sticky="nsew", padx=3, pady=3)
            ttk.Label(card, text=name, style="StatLabel.TLabel").pack(anchor="w")
            ttk.Label(card, textvariable=var, style="StatValue.TLabel", font=("Consolas", 11, "bold")).pack(anchor="w", pady=(2, 0))

        if HAS_MPL:
            self.graph_frame = ttk.Frame(main, style="Card.TFrame", padding=5)
            self.graph_frame.pack(fill="both", expand=True, pady=(0, 10))
            
            self.fig = Figure(figsize=(5, 2), dpi=100, facecolor="#252525")
            self.ax = self.fig.add_subplot(111)
            self.ax.set_facecolor("#1a1a1a")
            self.ax.tick_params(colors="white")
            for spine in self.ax.spines.values(): spine.set_color("#444")
            self.ax.set_ylabel("°C", color="#00e676")
            self.ax.grid(True, color="#333", linestyle="--")
            
            self.line, = self.ax.plot([], [], color="#ff1744", linewidth=2)
            self.canvas = FigureCanvasTkAgg(self.fig, master=self.graph_frame)
            self.canvas.get_tk_widget().pack(fill="both", expand=True)
        else:
            ttk.Label(main, text="pip install matplotlib для графика", style="Sub.TLabel").pack()

        self.timer_var = tk.StringVar(value="05:00")
        self.timer_lbl = ttk.Label(main, textvariable=self.timer_var, style="Timer.TLabel", anchor="center")
        self.timer_lbl.pack(fill="x", pady=(5, 5))

        bf = ttk.Frame(main)
        bf.pack(fill="x")
        self.start_btn = ttk.Button(bf, text="НАЧАТЬ", style="Start.TButton", command=self.start)
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.stop_btn = ttk.Button(bf, text="СТОП", style="Stop.TButton", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        self.save_btn = ttk.Button(main, text="СОХРАНИТЬ ОТЧЕТ", style="Action.TButton", command=self.save_report, state="disabled")
        self.save_btn.pack(fill="x", pady=(10, 0))

    def start(self):
        if self.is_running: return
        target = self.load_target.get() / 100.0
        self.is_running = True
        self.mp_stop.clear()
        self.save_btn.configure(state="disabled")
        
        self.time_left = self.time_target.get()
        self._update_timer()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.gpu_status_var.set("Запуск...")

        self.max_temp = 0
        self.avg_temp_sum = 0
        self.avg_temp_count = 0
        self.temp_history.clear()
        self.max_temp_var.set("0°C")

        cores = os.cpu_count() or 4
        for i in range(cores * 2):
            p = mp.Process(target=cpu_burner, args=(self.mp_stop, target, i), daemon=True)
            p.start()
            self.cpu_procs.append(p)
        self.workers_var.set(str(cores * 2))

        p = mp.Process(target=gpu_burner, args=(self.mp_stop, target, self.status_q), daemon=True)
        p.start()
        self.gpu_proc = p
        self._tick()

    def stop(self, auto=False, safety=False, reason=""):
        if not self.is_running: return
        self.is_running = False
        self.mp_stop.set()
        if self.timer_job: self.root.after_cancel(self.timer_job)
        
        for p in self.cpu_procs:
            p.join(timeout=1)
            if p.is_alive(): p.terminate()
        self.cpu_procs = []
        
        if self.gpu_proc:
            self.gpu_proc.join(timeout=1)
            if self.gpu_proc.is_alive(): self.gpu_proc.terminate()
            self.gpu_proc = None

        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.save_btn.configure(state="normal")
        self.cpu_load_var.set("—")
        self.gpu_load_var.set("—")
        self.gpu_temp_var.set("—")
        self.workers_var.set("0")
        self.timer_var.set("00:00")
        self.gpu_status_var.set("Ожидание...")

        if auto: messagebox.showinfo("Готово", "Тест завершён по таймеру.")
        elif safety: messagebox.showwarning("Стоп", f"{reason}\n\nНагрузка снята.")

    def _tick(self):
        if not self.is_running: return
        self.time_left -= 1
        self._update_timer()
        if self.time_left <= 0: self.stop(auto=True)
        else: self.timer_job = self.root.after(1000, self._tick)

    def _update_timer(self):
        m, s = divmod(self.time_left, 60)
        self.timer_var.set(f"{m:02d}:{s:02d}")

    def _update_monitor(self):
        try:
            if self.is_running:
                if HAS_PSUTIL:
                    self.cpu_load_var.set(f"{psutil.cpu_percent():.0f}%")
                
                self.gpu_load_var.set(MONITOR_DATA["load"])
                temp_str = MONITOR_DATA["temp"]
                self.gpu_temp_var.set(f"{temp_str}°C" if isinstance(temp_str, int) else temp_str)
                
                if isinstance(temp_str, int):
                    if temp_str > self.max_temp:
                        self.max_temp = temp_str
                        self.max_temp_var.set(f"{self.max_temp}°C")
                    
                    self.avg_temp_sum += temp_str
                    self.avg_temp_count += 1
                    
                    self.temp_history.append(temp_str)
                    if HAS_MPL:
                        self.line.set_data(range(len(self.temp_history)), self.temp_history)
                        self.ax.relim()
                        self.ax.autoscale_view()
                        self.canvas.draw()

                    if temp_str >= self.WARN_TEMP and HAS_SOUND:
                        winsound.Beep(1000, 200)
                    if temp_str >= self.TEMP_LIMIT:
                        self.stop(safety=True, reason=f"Критический перегрев: {temp_str}°C")
                        return

                try:
                    while True:
                        k, msg, ok = self.status_q.get_nowait()
                        if k == "GL_RENDERER":
                            if ok: self.gpu_status_var.set("OK")
                            else: self.gpu_status_var.set("INTEL (Встройка)!")
                except: pass
        finally:
            self.root.after(1000, self._update_monitor)

    def save_report(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
            initialfile="stress_test_report.txt",
            title="Сохранить отчет"
        )
        if not filepath: return

        avg_temp = round(self.avg_temp_sum / self.avg_temp_count, 1) if self.avg_temp_count > 0 else 0
        
        report = f"""==========================================
ОТЧЕТ О СТРЕСС-ТЕСТЕ (PRO STRESS TEST v9.1)
==========================================
Дата теста: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

--- ХАРАКТЕРИСТИКИ ПК ---
Процессор: {self.cpu_name}
Логических потоков: {os.cpu_count()}
Видеокарта: {self.nv_name} (Вендор: {self.gpu_vendor})
Всего ОЗУ: {round(psutil.virtual_memory().total / (1024**3), 1) if HAS_PSUTIL else 'N/A'} ГБ

--- ПАРАМЕТРЫ ТЕСТА ---
Целевая нагрузка: {self.load_target.get()}%
Длительность теста: {self.time_target.get() // 60} мин.

--- РЕЗУЛЬТАТЫ ОХЛАЖДЕНИЯ ---
Максимальная температура GPU: {self.max_temp} °C
Средняя температура GPU: {avg_temp} °C
Статус: {'ПРОЙДЕН (Без перегрева)' if self.max_temp < self.TEMP_LIMIT else 'ПРОВАЛЕН (Перегрев)'}

==========================================
"""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(report)
            messagebox.showinfo("Успех", f"Отчет сохранен:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить: {e}")

    def on_close(self):
        global STOP_MONITOR_THREAD
        STOP_MONITOR_THREAD = True
        if self.is_running:
            if not messagebox.askyesno("Выход", "Остановить тест и выйти?"): return
            self.stop()
        self.root.destroy()

if __name__ == "__main__":
    mp.freeze_support()
    root = tk.Tk()
    app = StressTestApp(root)
    root.mainloop()