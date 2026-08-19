"""Light/dark theme application and toggling."""

from tkinter import ttk

from videodownloader.optional_deps import sv_ttk
from videodownloader.constants import THEME_COLORS
from videodownloader.config import update_config


class ThemeMixin:
    def _apply_theme(self, mode):
        """mode is 'light' or 'dark'. Applies sv_ttk if available and sets
        up fonts/sizes for the plain (non-ttk) widgets that need it done
        by hand, namely the log text box."""
        self.theme_mode = mode
        colors = THEME_COLORS[mode]

        if sv_ttk is not None:
            sv_ttk.set_theme(mode)
        else:
            # Fallback for machines without sv-ttk installed: best available
            # built-in ttk theme, still themed consistently even if plainer.
            style = ttk.Style()
            if "clam" in style.theme_names():
                style.theme_use("clam")

        style = ttk.Style()
        style.configure(".", font=(self.ui_font, 10))
        style.configure("Heading.TLabel", font=(self.ui_font, 15, "bold"))
        style.configure("Muted.TLabel", foreground=colors["muted"], font=(self.ui_font, 9))
        style.configure("Section.TLabelframe.Label", font=(self.ui_font, 10, "bold"))

        # The log box is a plain tk.Text, so sv_ttk can't theme it. Keep it
        # in sync by hand whenever the theme changes.
        if hasattr(self, "log_text"):
            self.log_text.configure(
                background=colors["bg"],
                foreground=colors["fg"],
                insertbackground=colors["fg"],
                highlightbackground=colors["border"],
                highlightcolor=colors["border"],
            )

    def _toggle_theme(self):
        new_mode = "dark" if self.theme_mode == "light" else "light"
        self._apply_theme(new_mode)
        self.theme_btn.configure(text="Light mode" if new_mode == "dark" else "Dark mode")
        update_config(theme=new_mode)
