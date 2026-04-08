---
name: qt-python
description: Use when working on the Qt/PySide6 desktop application — UI changes, widgets, threading, stylesheets
user-invocable: true
disable-model-invocation: false
allowed-tools: Read Edit Write Grep Glob
---

# Qt Python Developer Skill

Apply these rules whenever working on the desktop application.

## Framework
- Use **PySide6** (not PyQt6) — imports are `from PySide6 import QtWidgets, QtCore, QtGui`.

## UI Files
- Build UI layouts with Qt Designer, save as `.ui` files.
- Load them in Python via `uic.loadUi()`:
  ```python
  from PySide6 import uic
  uic.loadUi("ui/my_widget.ui", self)
  ```
- Do not hand-code widget layouts in Python when a `.ui` file can be used instead.

## Threading
- Never run long-running work (DB queries, file I/O, model inference) on the main thread.
- Use `QThread` for stateful workers with signals:
  ```python
  class MyWorker(QtCore.QThread):
      result_ready = QtCore.Signal(object)
      def run(self):
          data = do_heavy_work()
          self.result_ready.emit(data)
  ```
- Use `QRunnable` + `QThreadPool` for fire-and-forget tasks.
- Always connect worker signals to slots on the main thread for UI updates.

## Stylesheets
- All QSS rules belong in `assets/style.qss` — do not inline `setStyleSheet()` calls for anything beyond transient state changes (e.g. validation feedback).
- Load the global stylesheet once in `MainWindow.__init__`:
  ```python
  with open("assets/style.qss") as f:
      self.setStyleSheet(f.read())
  ```

## General conventions
- Prefer signals/slots over direct method calls between widgets.
- Use `QtCore.Qt.ConnectionType.QueuedConnection` when connecting across threads.
- Keep widget classes thin — business logic lives in the service layer (`src/services/`), not in widget files.
