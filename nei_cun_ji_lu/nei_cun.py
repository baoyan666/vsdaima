# -*- coding: utf-8 -*-
"""磁盘空间记录器：点击"记录"，以表格形式记录 C 盘和 D 盘的剩余空间，
同时写入同一个 CSV（每次启动自动读取旧数据，新记录追加在下面），并支持填写备注。
支持列排序、日期筛选、定时自动记录。"""
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
TIME_COL = 0  # 记录时间列索引
# 数字列索引（排序时按数值排序）
NUM_COLS = {2, 3, 4}  # 总容量、已用、剩余


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
    """读取 CSV，返回 (数据行, 是否需要整体重写)。兼容没有"备注"列的旧文件。"""
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
        self.geometry("820x500")
        self.minsize(680, 300)
        self.all_data = []  # 所有记录的完整数据（用于 CSV 持久化）
        self.need_rewrite = False
        self.sort_reverse = {}  # 每列的排序方向
        self.auto_timer_id = None  # 定时自动记录的 timer id
        self.auto_running = False

        # --- 第一行工具栏：备注 + 记录 + 导出 ---
        row1 = ttk.Frame(self, padding=10)
        row1.pack(fill="x")
        ttk.Label(row1, text="备注：").pack(side="left")
        self.note_var = tk.StringVar()
        entry = ttk.Entry(row1, textvariable=self.note_var, width=32)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self.record())
        ttk.Button(row1, text="记录", command=self.record).pack(side="left", padx=8)
        ttk.Button(row1, text="导出 CSV", command=self.export).pack(side="left")

        # --- 第二行工具栏：日期筛选 ---
        row2 = ttk.Frame(self, padding=(10, 0, 10, 5))
        row2.pack(fill="x")
        ttk.Label(row2, text="日期筛选：").pack(side="left")
        ttk.Label(row2, text="从").pack(side="left", padx=(4, 2))
        self.start_date_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.start_date_var, width=12).pack(side="left")
        ttk.Label(row2, text="至").pack(side="left", padx=(4, 2))
        self.end_date_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.end_date_var, width=12).pack(side="left")
        ttk.Button(row2, text="筛选", command=self.filter_by_date).pack(side="left", padx=4)
        ttk.Button(row2, text="清除", command=self.clear_filter).pack(side="left")

        # --- 第三行工具栏：定时自动记录 ---
        row3 = ttk.Frame(self, padding=(10, 0, 10, 5))
        row3.pack(fill="x")
        ttk.Label(row3, text="定时记录：").pack(side="left")
        ttk.Label(row3, text="间隔").pack(side="left", padx=(4, 2))
        self.interval_var = tk.StringVar(value="30")
        ttk.Spinbox(row3, from_=1, to=1440, textvariable=self.interval_var, width=5).pack(side="left")
        ttk.Label(row3, text="分钟").pack(side="left", padx=2)
        self.auto_btn = ttk.Button(row3, text="启动", command=self.toggle_auto_record)
        self.auto_btn.pack(side="left", padx=8)

        # --- 表格 ---
        frame = ttk.Frame(self, padding=(10, 0, 10, 10))
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=HEADERS, show="headings")
        for h in HEADERS:
            width = 150 if h == "记录时间" else 180 if h == "备注" else 90
            self.tree.heading(h, text=h, command=lambda col=h: self.sort_column(col))
            self.tree.column(h, width=width, anchor="w" if h == "备注" else "center")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.edit_note)

        # --- 状态栏 ---
        self.status = tk.StringVar(value='记录文件：{}（双击"备注"单元格可修改，点击表头排序）'.format(LOG_FILE))
        ttk.Label(self, textvariable=self.status, padding=8).pack(fill="x")

        self.load_history()

    def add_row(self, row, index=None):
        """添加一行到 Treeview。index 为在 all_data 中的索引，用作 iid。"""
        if index is None:
            index = len(self.all_data) - 1
        self.tree.insert("", "end", iid=str(index), values=row)

    def refresh_tree(self, rows_with_indices=None):
        """刷新 Treeview 显示。rows_with_indices 为 [(index, row), ...]，默认显示全部。"""
        self.tree.delete(*self.tree.get_children())
        if rows_with_indices is None:
            rows_with_indices = enumerate(self.all_data)
        for idx, row in rows_with_indices:
            self.tree.insert("", "end", iid=str(idx), values=row)

    def all_rows(self):
        return self.all_data

    def load_history(self):
        try:
            rows, self.need_rewrite = read_log()
        except OSError as e:
            messagebox.showerror("读取失败", f"无法读取记录文件：\n{e}")
            return
        self.all_data = rows
        self.refresh_tree()
        self.tree.yview_moveto(1)
        self.status.set(f"已载入 {len(rows)} 条历史记录 | {LOG_FILE}")

    def record(self):
        note = self.note_var.get().strip()
        rows = [read_drive(d) + [note] for d in DRIVES]
        start_idx = len(self.all_data)
        for r in rows:
            self.all_data.append(r)
        # 如果有筛选条件，重新应用筛选；否则直接添加新行
        if self.start_date_var.get().strip() or self.end_date_var.get().strip():
            self.filter_by_date()
        else:
            for i, r in enumerate(rows):
                self.add_row(r, index=start_idx + i)
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

    # ---------- 列排序 ----------
    def sort_column(self, col):
        """点击表头排序：数字列按数值，百分比列按数值，其他按字符串，升序/降序切换。"""
        col_idx = HEADERS.index(col)
        reverse = self.sort_reverse.get(col, False)

        # 获取当前显示的行
        items = [(self.tree.set(iid, col), iid) for iid in self.tree.get_children()]

        def sort_key(item):
            val = item[0]
            if col_idx in NUM_COLS:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return 0.0
            if col_idx == 5:  # 剩余比例，如 "45.2%"
                try:
                    return float(val.rstrip("%"))
                except (ValueError, TypeError):
                    return 0.0
            return val

        items.sort(key=sort_key, reverse=reverse)

        # 重新排列 Treeview
        for idx, (_, iid) in enumerate(items):
            self.tree.move(iid, "", idx)

        # 切换排序方向，更新表头箭头
        self.sort_reverse[col] = not reverse
        arrow = " ↓" if not reverse else " ↑"
        for h in HEADERS:
            text = h + arrow if h == col else h
            self.tree.heading(h, text=text, command=lambda c=h: self.sort_column(c))

    # ---------- 日期筛选 ----------
    def filter_by_date(self):
        """按日期范围筛选记录。"""
        start = self.start_date_var.get().strip()
        end = self.end_date_var.get().strip()
        if not start and not end:
            self.clear_filter()
            return
        # 校验日期格式
        try:
            if start:
                datetime.strptime(start, "%Y-%m-%d")
            if end:
                datetime.strptime(end, "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("格式错误", "日期格式应为 YYYY-MM-DD，例如 2025-01-01")
            return

        filtered = []
        for idx, row in enumerate(self.all_data):
            date_str = row[TIME_COL][:10]  # 取 "YYYY-MM-DD" 部分
            if start and date_str < start:
                continue
            if end and date_str > end:
                continue
            filtered.append((idx, row))

        self.refresh_tree(filtered)
        self.tree.yview_moveto(1)
        self.status.set(f"筛选结果：{len(filtered)} 条（共 {len(self.all_data)} 条）| {LOG_FILE}")

    def clear_filter(self):
        """清除筛选，显示全部记录。"""
        self.start_date_var.set("")
        self.end_date_var.set("")
        self.refresh_tree()
        self.tree.yview_moveto(1)
        self.status.set(f"共 {len(self.all_data)} 条记录 | {LOG_FILE}")

    # ---------- 定时自动记录 ----------
    def toggle_auto_record(self):
        """切换定时自动记录的启动/停止。"""
        if self.auto_running:
            self.stop_auto_record()
        else:
            self.start_auto_record()

    def start_auto_record(self):
        """启动定时自动记录。"""
        try:
            interval = int(self.interval_var.get())
            if interval < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("间隔无效", "请输入 1~1440 之间的整数（分钟）")
            return
        self.auto_running = True
        self.auto_btn.config(text="停止")
        self._schedule_auto(interval)
        self.status.set(f"自动记录中，每 {interval} 分钟 | {LOG_FILE}")

    def _schedule_auto(self, interval_min):
        """安排下一次自动记录。"""
        self.auto_timer_id = self.after(interval_min * 60 * 1000, self._auto_record_tick)

    def _auto_record_tick(self):
        """定时器触发：执行记录并安排下一次。"""
        if not self.auto_running:
            return
        self.record()
        interval = int(self.interval_var.get())
        self._schedule_auto(interval)

    def stop_auto_record(self):
        """停止定时自动记录。"""
        if self.auto_timer_id is not None:
            self.after_cancel(self.auto_timer_id)
            self.auto_timer_id = None
        self.auto_running = False
        self.auto_btn.config(text="启动")
        self.status.set(f"自动记录已停止 | {LOG_FILE}")

    # ---------- 编辑备注 ----------
    def edit_note(self, event):
        """双击"备注"单元格，直接修改文字，回车保存，Esc 取消。"""
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
        # 通过 iid 找到 all_data 中的索引
        idx = int(item)
        entry.insert(0, self.all_data[idx][NOTE_COL])
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
            self.all_data[idx][NOTE_COL] = text
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
