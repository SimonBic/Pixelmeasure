import sys
from PySide6.QtWidgets import QApplication
from userinterface import MainWindow
from theme import QSS

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())