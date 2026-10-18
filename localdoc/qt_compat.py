"""Qt6 on Windows; Qt5 on legacy macOS. Only one binding is installed per build."""
try:
    from PySide6 import QtCore, QtWidgets
    QT_BINDING = 'PySide6'
except ImportError:
    from PySide2 import QtCore, QtWidgets
    QT_BINDING = 'PySide2'

Qt, QThread, Signal = QtCore.Qt, QtCore.QThread, QtCore.Signal
QMainWindow = QtWidgets.QMainWindow
QWidget = QtWidgets.QWidget
QVBoxLayout = QtWidgets.QVBoxLayout
QHBoxLayout = QtWidgets.QHBoxLayout
QPushButton = QtWidgets.QPushButton
QFileDialog = QtWidgets.QFileDialog
QMessageBox = QtWidgets.QMessageBox
QTableWidget = QtWidgets.QTableWidget
QTableWidgetItem = QtWidgets.QTableWidgetItem
QAbstractItemView = QtWidgets.QAbstractItemView
QFormLayout = QtWidgets.QFormLayout
QLineEdit = QtWidgets.QLineEdit
QPlainTextEdit = QtWidgets.QPlainTextEdit
QLabel = QtWidgets.QLabel
QComboBox = QtWidgets.QComboBox
QCheckBox = QtWidgets.QCheckBox
QProgressBar = QtWidgets.QProgressBar

class QApplication(QtWidgets.QApplication):
    def exec(self):
        if QT_BINDING == 'PySide2':
            return super().exec_()
        return super().exec()

class QDialog(QtWidgets.QDialog):
    def exec(self):
        if QT_BINDING == 'PySide2':
            return super().exec_()
        return super().exec()
