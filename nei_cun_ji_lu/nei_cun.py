# -*- coding: utf-8 -*-
"""磁盘空间记录器：点击“记录”，以表格形式记录 C 盘和 D 盘的剩余空间，
同时写入同一个 CSV（每次启动自动读取旧数据，新记录追加在下面），并支持填写备注。"""
import csv
import os
import shutil
import sys
import tkinter as tk
import unicodedata
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

DRIVES = ["C:\\", "D:\\"]
HEADERS = ["记录时间", "磁盘", "总容量(GB)", "已用(GB)", "剩余(GB)", "剩余比例", "备注"]
NOTE_COL = len(HEADERS) - 1


def app_dir():
    if getattr(sys, "frozen", False):  # 打包成 exe 后
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


LOG_FILE = os.path.join(app_dir(), "磁盘空间记录.csv")


def gb(n):
    return f"{n / 1024 ** 3:.2f}"


def read_drive(drive):
    """返回一行记录（不含备注）；磁盘不存在时显示 '不存在'。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        total, used, free = shutil.disk_usage(drive)
        return [now, drive[:2], gb(total), gb(used), gb(free), f"{free / total:.1%}"]
    except (FileNotFoundError, OSError):
        return [now, drive[:2], "不存在", "-", "-", "-"]


# ---------- CSV 读写 ----------
def read_log(path=LOG_FILE):
    """读取 CSV，返回 (数据行, 是否需要整体重写)。兼容没有“备注”列的旧文件。"""
    if not os.path.exists(path):
        return [], False
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.reader(f) if r]
    if not rows:
        return [], True
    header, data = rows[0], rows[1:]
    need_rewrite = header != HEADERS
    data = [(r + [""] * len(HEADERS))[: len(HEADERS)] for r in data]
    return data, need_rewrite


def write_log(rows, path=LOG_FILE):
    """整体重写 CSV（先写临时文件再替换，避免写一半损坏）。"""
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(HEADERS)
        w.writerows(rows)
    os.replace(tmp, path)


def append_log(rows, path=LOG_FILE):
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(rows)


# ---------- 终端打印 ----------
def disp_width(text):
    """中文字符占 2 格，保证终端表格对齐。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(text))


def print_table(rows):
    """在终端（VS Code 调试控制台 / 终端）打印表格。"""
    data = [HEADERS] + rows
    widths = [max(disp_width(r[i]) for r in data) for i in range(len(HEADERS))]
    line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def fmt(r):
        cells = [" " + str(c) + " " * (w - disp_width(c) + 1) for c, w in zip(r, widths)]
        return "|" + "|".join(cells) + "|"

    print(line)
    print(fmt(HEADERS))
    print(line)
    for r in rows:
        print(fmt(r))
    print(line, flush=True)


# ---------- 界面 ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("磁盘空间记录器")
        self.geometry("820x440")
        self.minsize(680, 300)
        self.data = {}  # 表格行 id -> 该行原始字符串列表（避免 Treeview 自动转换数字）
        self.need_rewrite = False

        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="备注：").pack(side="left")
        self.note_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.note_var, width=32)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self.record())
        ttk.Button(top, text="记录", command=self.record).pack(side="left", padx=8)
        ttk.Button(top, text="导出 CSV", command=self.export).pack(side="left")

        frame = ttk.Frame(self, padding=(10, 0, 10, 0))
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=HEADERS, show="headings")
        for h in HEADERS:
            width = 150 if h == "记录时间" else 180 if h == "备注" else 90
            self.tree.heading(h, text=h)
            self.tree.column(h, width=width, anchor="w" if h == "备注" else "center")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.edit_note)

        self.status = tk.StringVar(value=f"记录文件：{LOG_FILE}（双击“备注”单元格可修改）")
        ttk.Label(self, textvariable=self.status, padding=8).pack(fill="x")

        self.load_history()

    def add_row(self, row):
        iid = self.tree.insert("", "end", values=row)
        self.data[iid] = list(row)

    def all_rows(self):
        return [self.data[i] for i in self.tree.get_children()]

    def load_history(self):
        try:
            rows, self.need_rewrite = read_log()
        except OSError as e:
            messagebox.showerror("读取失败", f"无法读取记录文件：\n{e}")
            return
        for r in rows:
            self.add_row(r)
        self.tree.yview_moveto(1)
        self.status.set(f"已载入 {len(rows)} 条历史记录 | {LOG_FILE}")

    def record(self):
        note = self.note_var.get().strip()
        rows = [read_drive(d) + [note] for d in DRIVES]
        for r in rows:
            self.add_row(r)
        self.tree.yview_moveto(1)
        print_table(rows)  # 同时在终端打印
        try:
            if self.need_rewrite or not os.path.exists(LOG_FILE):
                write_log(self.all_rows())
                self.need_rewrite = False
            else:
                append_log(rows)
            self.note_var.set("")
            self.status.set("已记录  " + "  |  ".join(f"{r[1]} 剩余 {r[4]} GB" for r in rows))
        except OSError as e:
            messagebox.showerror("保存失败", f"无法写入记录文件（是否被 Excel 打开了？）：\n{e}")

    def edit_note(self, event):
        """双击“备注”单元格，直接修改文字，回车保存，Esc 取消。"""
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != f"#{NOTE_COL + 1}":
            return
        item = self.tree.identify_row(event.y)
        box = self.tree.bbox(item, f"#{NOTE_COL + 1}") if item else ""
        if not box:
            return
        x, y, w, h = box
        entry = ttk.Entry(self.tree)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, self.data[item][NOTE_COL])
        entry.select_range(0, "end")
        entry.focus_set()
        done = []

        def finish(save):
            if done:
                return
            done.append(1)
            text = entry.get().strip()
            entry.destroy()
            if not save:
                return
            self.data[item][NOTE_COL] = text
            self.tree.set(item, HEADERS[NOTE_COL], text)
            try:
                write_log(self.all_rows())
                self.need_rewrite = False
                self.status.set("备注已保存")
            except OSError as e:
                messagebox.showerror("保存失败", f"无法写入记录文件（是否被 Excel 打开了？）：\n{e}")

        entry.bind("<Return>", lambda e: finish(True))
        entry.bind("<FocusOut>", lambda e: finish(True))
        entry.bind("<Escape>", lambda e: finish(False))

    def export(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")], initialfile="磁盘空间记录_导出.csv"
        )
        if not path:
            return
        try:
            write_log(self.all_rows(), path)
            self.status.set(f"已导出到：{path}")
        except OSError as e:
            messagebox.showerror("导出失败", str(e))


if __name__ == "__main__":
    App().mainloop()