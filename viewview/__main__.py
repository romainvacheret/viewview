import sys

from PySide6 import QtCore, QtWidgets
from PySide6 import QtGui


class CustomWidget(QtWidgets.QWidget):
    def __init__(self):

        super().__init__()
        layout = QtWidgets.QVBoxLayout(self) 
        img_path = '/Users/romain/Pictures/Wallpaper1.jpg'
        reader = QtGui.QImageReader(img_path)

        loaded_img = reader.read()
        pixel_map = QtGui.QPixmap.fromImage(loaded_img)

        img_label = QtWidgets.QLabel()
        img_label.setPixmap(pixel_map)
        img_label.setScaledContents(True)
         

        layout.addWidget(img_label)

        self.setLayout(layout)


if __name__ == '__main__':
    app = QtWidgets.QApplication([])

    widget = CustomWidget()
    widget.showMaximized()

    sys.exit(app.exec())
