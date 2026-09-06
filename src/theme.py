QSS = """
QMainWindow, QWidget {
    background-color: #F5F7FA;
    color: #1F2937;
    font-size: 14px;
    font-family: "Latin Modern Roman", "CMU Serif", serif;
}

QWidget#knopf_spalte {
    background-color: #FFFFFF;
    border-right: 1px solid #D8DEE6;
}

QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                 stop:0 #FFFFFF, stop:1 #EDF2F8);
    color: #1F2937;
    border: 2px solid #4A90D9;
    border-radius: 10px;
    padding: 8px;
    font-weight: 500;
}

QPushButton#overlay_button {
    border-radius: 0px;
}

QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                 stop:0 #9CBFE2, stop:1 #7FA5C9);
    color: #FFFFFF;
}

QPushButton:pressed {
    background-color: #4A90D9;
    color: #FFFFFF;
    border-color: #3A73AD;
}

QPushButton:disabled {
    background-color: #EDEFF2;
    color: #A0A6AE;
    border-color: #C7CDD4;
}

QLabel {
    color: #1F2937;
    font-size: 25px;
}

 QScrollBar:vertical {
    background: transparent;
    width: 14px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #4A90D9;
    border-radius: 2px;
    min-height: 20px;
    margin: 0px 4.5px 0px 4.5px;
}
QScrollBar::handle:vertical:hover {
    background: #3A73AD;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
 
QScrollBar:horizontal {
    background: transparent;
    height: 14px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #4A90D9;
    border-radius: 2px;
    min-width: 20px;
    margin: 4.5px 0px 4.5px 0px;
}
QScrollBar::handle:horizontal:hover {
    background: #3A73AD;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}
"""