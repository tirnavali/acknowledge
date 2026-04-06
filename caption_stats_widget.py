"""
CaptionStatsWidget — Displays inference performance statistics for the Captioning service.
Shows last 5 executions and historical averages.
"""
import os
from PySide6 import QtCore, QtWidgets, QtGui

class CaptionStatsWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._results = []
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Header
        header = QtWidgets.QLabel("📊 Altyazı Servisi Performans İstatistikleri")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #0078D7; margin-bottom: 10px;")
        layout.addWidget(header)

        # Summary Section
        summary_group = QtWidgets.QGroupBox("Genel İstatistikler")
        summary_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #3f3f46; margin-top: 10px; padding-top: 15px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }")
        summary_layout = QtWidgets.QGridLayout(summary_group)
        
        self.lbl_avg = QtWidgets.QLabel("Ortalama İşlem Süresi: ---")
        self.lbl_total = QtWidgets.QLabel("Toplam İşlem Sayısı: 0")
        
        self.lbl_avg.setStyleSheet("font-size: 14px; color: #ecf0f1;")
        self.lbl_total.setStyleSheet("font-size: 14px; color: #ecf0f1;")
        
        summary_layout.addWidget(self.lbl_total, 0, 0)
        summary_layout.addWidget(self.lbl_avg, 0, 1)
        layout.addWidget(summary_group)

        history_group = QtWidgets.QGroupBox("Son İşlemler")
        history_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #3f3f46; margin-top: 10px; padding-top: 15px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }")
        history_layout = QtWidgets.QVBoxLayout(history_group)

        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Dosya Adı", "Süre (sn)", "Durum"])
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(2, 100)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget { background-color: #252526; alternate-background-color: #2d2d30; gridline-color: #3f3f46; color: #ffffff; }
            QHeaderView::section { background-color: #333333; color: #ffffff; padding: 4px; border: 1px solid #3f3f46; }
        """)
        
        history_layout.addWidget(self.table)
        layout.addWidget(history_group)

        # Control buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_clear = QtWidgets.QPushButton("🔄 İstatistikleri Sıfırla")
        self.btn_clear.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_clear.setStyleSheet("QPushButton { background-color: #333333; } QPushButton:hover { background-color: #c0392b; }")
        self.btn_clear.clicked.connect(self.clear_stats)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_clear)
        layout.addLayout(btn_layout)

        layout.addStretch()

    def add_result(self, result):
        """Add a new CaptionResult to the statistics."""
        # Record ALL attempts for statistics count, even if they have errors
        self._results.append(result)
        self._update_display()

    def _update_display(self):
        # Update summary
        total_count = len(self._results)
        self.lbl_total.setText(f"Toplam İşlem Sayısı: {total_count}")
        
        if total_count > 0:
            avg_time = sum(r.duration for r in self._results) / total_count
            self.lbl_avg.setText(f"Ortalama İşlem Süresi: {avg_time:.2f} sn")
        else:
            self.lbl_avg.setText("Ortalama İşlem Süresi: ---")

        # Update table (last 5)
        last_5 = self._results[-5:]
        last_5.reverse()  # most recent first
        
        self.table.setRowCount(len(last_5))
        for i, res in enumerate(last_5):
            filename = os.path.basename(res.img_path)
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(filename))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(f"{res.duration:.2f}"))
            
            status = "Hata" if res.error else "Başarılı"
            status_item = QtWidgets.QTableWidgetItem(status)
            if res.error:
                status_item.setForeground(QtGui.QColor("#c0392b")) # red
            else:
                status_item.setForeground(QtGui.QColor("#27ae60")) # green
            self.table.setItem(i, 2, status_item)

    def clear_stats(self):
        self._results = []
        self._update_display()
