import tkinter as tk

from videodownloader.gui.main_window import maximize_window


class FakeRoot:
    def __init__(self, raise_on=None):
        self.calls = []
        self.raise_on = raise_on

    def state(self, value):
        self.calls.append(("state", value))
        if self.raise_on == "state":
            raise tk.TclError("unsupported")

    def attributes(self, name, value):
        self.calls.append(("attributes", name, value))
        if self.raise_on == "attributes":
            raise tk.TclError("unsupported")


def test_maximizes_via_state_zoomed_on_windows():
    root = FakeRoot()

    maximize_window(root, system="Windows")

    assert root.calls == [("state", "zoomed")]


def test_maximizes_via_attributes_zoomed_on_linux():
    root = FakeRoot()

    maximize_window(root, system="Linux")

    assert root.calls == [("attributes", "-zoomed", True)]


def test_unsupported_window_manager_is_swallowed_not_raised():
    root = FakeRoot(raise_on="state")

    maximize_window(root, system="Windows")  # must not raise
