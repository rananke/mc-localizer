#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minecraft Modpack Localizer v2.0 (GUI)
Переводит названия предметов и квесты. Не ломает сборку.
"""
import os, json, shutil, time, re, requests, threading, queue
import tkinter as tk
from tkinter import filedialog, ttk, messagebox, scrolledtext
from pathlib import Path

class MCLocalizerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Minecraft Modpack Localizer v2.0")
        self.root.geometry("720x560")
        self.root.resizable(False, False)

        self.log_queue = queue.Queue()
        self.is_running = False
        self.target_lang = tk.StringVar(value="ru")
        self.rate_limit = tk.DoubleVar(value=0.8)

        self._build_ui()
        self.root.after(100, self._poll_log_queue)

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text="📂 Путь к папке сборки Minecraft:").pack(anchor=tk.W)
        f_frame = ttk.Frame(main)
        f_frame.pack(fill=tk.X, pady=5)
        self.folder_var = tk.StringVar()
        ttk.Entry(f_frame, textvariable=self.folder_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(f_frame, text="Обзор...", command=self._select_folder).pack(side=tk.RIGHT)

        s_frame = ttk.Frame(main)
        s_frame.pack(fill=tk.X, pady=10)
        ttk.Label(s_frame, text="🌐 Язык:").pack(side=tk.LEFT)
        ttk.Combobox(s_frame, textvariable=self.target_lang, values=["ru","en","uk","kz","de","fr","es","zh","ja"], width=5, state="readonly").pack(side=tk.LEFT, padx=(5, 20))
        ttk.Label(s_frame, text="⏱ Задержка (сек):").pack(side=tk.LEFT)
        ttk.Entry(s_frame, textvariable=self.rate_limit, width=5).pack(side=tk.LEFT)

        ttk.Label(main, text="📜 Журнал:").pack(anchor=tk.W)
        self.log = scrolledtext.ScrolledText(main, height=16, state=tk.DISABLED, wrap=tk.WORD, font=("Consolas", 9))
        self.log.pack(fill=tk.BOTH, expand=True, pady=5)

        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=10)
        self.btn_start = ttk.Button(btn_frame, text="🚀 Начать перевод", command=self._start)
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.btn_stop = ttk.Button(btn_frame, text="⏹ Остановить", command=self._stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        self.status_var = tk.StringVar(value="✅ Готово к работе")
        ttk.Label(main, textvariable=self.status_var, foreground="#0055aa").pack(anchor=tk.W)

    def _select_folder(self):
        path = filedialog.askdirectory(title="Выберите корневую папку сборки")
        if path: self.folder_var.set(path)

    def _log(self, msg, lvl="INFO"):
        self.log_queue.put((msg, lvl))

    def _poll_log_queue(self):
        try:
            while True:
                msg, lvl = self.log_queue.get_nowait()
                self.log.config(state=tk.NORMAL)
                self.log.insert(tk.END, f"[{lvl}] {msg}\n")
                self.log.see(tk.END)
                self.log.config(state=tk.DISABLED)
        except queue.Empty: pass
        self.root.after(100, self._poll_log_queue)

    def _translate(self, text):
        if not text or len(text.strip()) < 2: return text
        if re.search(r'[§&]|%\d|\{[0-9a-zA-Z_]+\}', text): return text
        try:
            url = "https://translate.googleapis.com/translate_a/single"
            resp = requests.get(url, params={"client":"gtx","sl":"auto","tl":self.target_lang.get(),"dt":"t","q":text}, timeout=7)
            resp.raise_for_status()
            return "".join(i[0] for i in resp.json()[0] if isinstance(i, list) and i[0])
        except: return text

    def _process(self, fpath, backup_root, is_quest):
        rel = fpath.relative_to(Path(self.folder_var.get().strip().strip('"')))
        backup_path = backup_root / rel
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fpath, backup_path)

        try:
            with open(fpath, "r", encoding="utf-8") as f: data = json.load(f)
        except:
            self._log(f"⚠ Битый JSON: {fpath.name}", "WARN")
            return False

        modified = False
        if is_quest:
            keys = {"title","description","subtitle","tooltip","text","name","page_title","chapter_title"}
            def walk(obj):
                nonlocal modified
                if isinstance(obj, dict):
                    for k,v in obj.items():
                        if k in keys and isinstance(v, str):
                            nv = self._translate(v)
                            if nv != v: obj[k] = nv; modified = True
                        elif isinstance(v, (dict,list)): walk(v)
                elif isinstance(obj, list):
                    for i in obj: walk(i)
            walk(data)
        else:
            for k,v in data.items():
                if isinstance(v, str) and k != v:
                    nv = self._translate(v)
                    if nv != v: data[k] = nv; modified = True

        if modified:
            with open(fpath, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        return False

    def _start(self):
        p = self.folder_var.get().strip().strip('"')
        if not os.path.isdir(p):
            messagebox.showerror("Ошибка", "Папка не найдена.")
            return
        self.is_running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.status_var.set("⏳ Перевод запущен...")
        threading.Thread(target=self._worker, args=(p,), daemon=True).start()

    def _worker(self, pack_dir):
        backup = Path(pack_dir) / "_localization_backup"
        backup.mkdir(exist_ok=True)
        self._log(f"💾 Бэкап: {backup}")
        self._log("🔍 Сканирование...")
        cnt = 0
        skip = {"config","scripts","kubejs","mods","defaultconfigs","server","world","saves",".git",".idea"}
        delay = max(0.1, self.rate_limit.get())

        for root, dirs, files in os.walk(pack_dir):
            if not self.is_running: break
            dirs[:] = [d for d in dirs if d not in skip and not d.startswith(".")]
            for fn in files:
                if not self.is_running or not fn.endswith(".json"): continue
                fp = Path(root) / fn
                is_l = any(p == "lang" for p in fp.parts)
                is_q = "ftbquests" in fp.parts
                if is_l or is_q:
                    self._log(f"📄 {fp.relative_to(pack_dir)}")
                    if self._process(fp, backup, is_q): cnt += 1
                    time.sleep(delay)

        if self.is_running:
            self._log(f"✅ Готово. Обработано: {cnt} файлов")
            self.status_var.set("✅ Завершено успешно")
        else:
            self._log("⏹ Остановлено пользователем")
            self.status_var.set("⏹ Остановлено")
        self.is_running = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

    def _stop(self): self.is_running = False

if __name__ == "__main__":
    root = tk.Tk()
    MCLocalizerGUI(root)
    root.mainloop()
