"""Borderless corner notification shown after a download finishes/fails."""

import tkinter as tk

from videodownloader.constants import THEME_COLORS


class ToastMixin:
    def _show_toast(self, title, message, kind="info"):
        try:
            self.root.update_idletasks()
            colors = THEME_COLORS[self.theme_mode]
            accent = {"success": "#2ea043", "error": "#e5484d"}.get(kind, colors["fg"])

            toast = tk.Toplevel(self.root)
            toast.overrideredirect(True)
            toast.attributes("-topmost", True)

            frame = tk.Frame(toast, bg=colors["bg"], highlightbackground=accent, highlightthickness=2, bd=0)
            frame.pack(fill="both", expand=True)
            tk.Label(
                frame, text=title, bg=colors["bg"], fg=accent, font=(self.ui_font, 10, "bold"),
                anchor="w",
            ).pack(fill="x", padx=14, pady=(10, 2))
            tk.Label(
                frame, text=message, bg=colors["bg"], fg=colors["fg"], font=(self.ui_font, 9),
                anchor="w", justify="left", wraplength=300,
            ).pack(fill="x", padx=14, pady=(0, 10))

            toast.update_idletasks()
            w, h = toast.winfo_width(), toast.winfo_height()
            x = self.root.winfo_x() + self.root.winfo_width() - w - 24
            y = self.root.winfo_y() + self.root.winfo_height() - h - 24
            toast.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")

            toast.bind("<Button-1>", lambda e: toast.destroy())
            toast.after(4500, lambda: toast.destroy() if toast.winfo_exists() else None)
        except tk.TclError:
            pass  # main window may already be closing
