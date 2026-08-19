"""Borderless corner notification shown after a download finishes/fails."""

import tkinter as tk

from videodownloader.constants import THEME_COLORS

# Border/accent colors — bright, work fine as a 2px highlight border in
# both themes.
_TOAST_BORDER_COLORS = {"success": "#2ea043", "error": "#e5484d"}

# Title text needs to meet WCAG AA contrast (4.5:1) against each theme's
# background. The bright accent colors above pass on the dark background
# (~5:1+) but fall short on the light one (~3.3-3.8:1), so the light
# theme gets darker, text-safe variants here instead.
_TOAST_TEXT_COLORS = {
    "light": {"success": "#1a7f37", "error": "#cf222e"},
    "dark": _TOAST_BORDER_COLORS,
}


class ToastMixin:
    def _show_toast(self, title, message, kind="info"):
        try:
            self.root.update_idletasks()
            colors = THEME_COLORS[self.theme_mode]
            border_accent = _TOAST_BORDER_COLORS.get(kind, colors["fg"])
            text_accent = _TOAST_TEXT_COLORS[self.theme_mode].get(kind, colors["fg"])

            toast = tk.Toplevel(self.root)
            toast.overrideredirect(True)
            toast.attributes("-topmost", True)

            frame = tk.Frame(toast, bg=colors["bg"], highlightbackground=border_accent, highlightthickness=2, bd=0)
            frame.pack(fill="both", expand=True)
            tk.Label(
                frame, text=title, bg=colors["bg"], fg=text_accent, font=(self.ui_font, 10, "bold"),
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
