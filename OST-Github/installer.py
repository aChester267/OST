import os
import sys
import time
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

class FakeInstaller:
    def __init__(self, root):
        self.root = root
        self.root.title("Установка OST") # Изменено
        self.root.geometry("500x350")
        self.root.configure(bg="#121212")
        self.root.resizable(False, False)
        
        # Пути
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        self.source_exe = os.path.join(self.current_dir, "dist", "OST.exe")
        
        # Куда установим (папка OST в AppData)
        self.target_dir = os.path.join(os.environ['LOCALAPPDATA'], "OST") # Изменено
        self.target_exe = os.path.join(self.target_dir, "OST.exe")
        
        self._setup_ui()

    def _setup_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background="#121212", foreground="#ffffff", font=("Segoe UI", 10))
        
        # Заголовок
        tk.Label(self.root, text="OST", font=("Segoe UI", 18, "bold"), fg="#00e676", bg="#121212").pack(pady=(20, 5)) # Изменено
        tk.Label(self.root, text="Мастер установки", font=("Segoe UI", 10), fg="#888", bg="#121212").pack(pady=(0, 20))
        
        # Текст лицензии
        text_frame = tk.Frame(self.root, bg="#1e1e1e", bd=1, relief="solid")
        text_frame.pack(fill="x", padx=40, pady=10)
        tk.Label(text_frame, text="Нажмите «Установить», чтобы начать.\n\n• Программа скопирует файлы.\n• Создаст ярлык «OST» на рабочем столе.\n• Запустит приложение.", 
                 bg="#1e1e1e", fg="#ccc", justify="left").pack(padx=15, pady=15, anchor="w")

        # Прогресс-бар
        self.progress_var = tk.DoubleVar()
        self.progress = ttk.Progressbar(self.root, variable=self.progress_var, maximum=100)
        self.progress.pack(fill="x", padx=40, pady=(20, 5))
        
        self.status_label = tk.Label(self.root, text="Ожидание...", font=("Segoe UI", 9), fg="#888", bg="#121212")
        self.status_label.pack(pady=(0, 15))

        # Кнопка
        self.install_btn = tk.Button(self.root, text="УСТАНОВИТЬ", font=("Segoe UI", 11, "bold"), bg="#00e676", fg="#000", 
                                     activebackground="#00c853", activeforeground="#000", bd=0, padx=20, pady=8, cursor="hand2",
                                     command=self.start_install)
        self.install_btn.pack(pady=10)

    def start_install(self):
        self.install_btn.config(state="disabled", text="УСТАНОВКА...")
        
        if not os.path.exists(self.source_exe):
            messagebox.showerror("Ошибка", f"Не найден файл OST.exe!\nУбедитесь, что он лежит в папке dist.\nПуть: {self.source_exe}")
            self.install_btn.config(state="normal", text="УСТАНОВИТЬ")
            return

        threading.Thread(target=self.install_process, daemon=True).start()

    def install_process(self):
        steps = [
            (10, "Подготовка к установке..."),
            (30, "Распаковка компонентов..."),
            (50, "Копирование файлов (1/2)..."),
            (70, "Копирование файлов (2/2)..."),
            (85, "Создание ярлыка «OST»..."),
            (100, "Завершение установки...")
        ]

        for percent, text in steps:
            self.status_label.config(text=text)
            self.progress_var.set(percent)
            time.sleep(0.8)

            if percent == 50:
                os.makedirs(self.target_dir, exist_ok=True)
            elif percent == 70:
                shutil.copy2(self.source_exe, self.target_exe)
            elif percent == 85:
                self.create_shortcut()

        self.status_label.config(text="Установка завершена!", fg="#00e676")
        messagebox.showinfo("Успех", "Программа OST успешно установлена!")
        
        os.startfile(self.target_exe)
        self.root.quit()

    def create_shortcut(self):
        desktop_path = os.path.join(os.path.join(os.environ['USERPROFILE']), 'Desktop')
        shortcut_path = os.path.join(desktop_path, "OST.lnk") # Изменено на OST
        
        if not os.path.exists(desktop_path):
            desktop_path = os.path.join(os.environ['USERPROFILE'], 'OneDrive', 'Desktop')
            shortcut_path = os.path.join(desktop_path, "OST.lnk")

        ps_script = f"""
        $WshShell = New-Object -ComObject WScript.Shell
        $Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
        $Shortcut.TargetPath = "{self.target_exe}"
        $Shortcut.WorkingDirectory = "{self.target_dir}"
        $Shortcut.IconLocation = "{self.target_exe},0"
        $Shortcut.Save()
        """
        
        try:
            subprocess.run(["powershell", "-Command", ps_script], 
                           creationflags=subprocess.CREATE_NO_WINDOW, 
                           check=True)
        except Exception as e:
            print(f"Ошибка при создании ярлыка: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = FakeInstaller(root)
    root.mainloop()
