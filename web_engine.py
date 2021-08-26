"""
Usage:
------
\tpython3 <url> <filename.pdf/filepath>
"""

from PyQt5 import QtCore, QtWidgets, QtWebEngineWidgets
import sys, os
print(sys.argv)
web_app = QtWidgets.QApplication(sys.argv)
loader = QtWebEngineWidgets.QWebEngineView()
loader.page().pdfPrintingFinished.connect(loader.close)
loader.load(QtCore.QUrl(sys.argv[1]))

def emit_pdf(finished):
    if not os.path.exists('reports'):
        os.mkdir('reports')
    loader.page().printToPdf('reports/'+sys.argv[2])

loader.loadFinished.connect(emit_pdf)
web_app.exec()