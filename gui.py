"""A Qt GUI for editing and rendering DrawTime timing diagrams."""

import re
import time
from PyQt4 import QtCore, QtGui
import parse
import render


# The path to the application icon.
ICON_PATH = 'data/drawtime.png'

# The URL to which the Help menu button leads.
HELP_URL = 'http://max99x.com/school/drawtime'

# The background color of lines that contain errors.
ERROR_BACKGROUND = QtGui.QColor('#ffdddd')

# The value of Editor.preview_mode that represents instant (live) preview.
PREVIEW_INSTANT = object()
# The value of Editor.preview_mode that represents delayed preview.
PREVIEW_DELAYED = object()
# The value of Editor.preview_mode that represents no automatic preview.
PREVIEW_MANUAL = object()
# The length of time in seconds after an editing action before a delayed preview
# is triggered. Fractions are supported if the time module provides them.
PREVIEW_DELAY = 2
# The number of milliseconds between ticks of the timer that checks whether a
# delayed preview should be triggered.
PREVIEW_TIMER_RESOLUTION = 50


class Editor(QtGui.QMainWindow):
  """The main DrawTime editor window."""

  def __init__(self):
    super().__init__()

    self.setupMenu()
    self.setupEditor()
    self.setupCanvas()
    self.setupSize()
    self.statusBar()
    self.setWindowIcon(QtGui.QIcon(ICON_PATH))

    self.filepath = None
    self.saved = True
    self.preview_mode = PREVIEW_INSTANT
    self.last_action_time = None
    self.preview_timer = None

    self.markSaved()

  def setupMenu(self):
    """Creates the menu bar and binds actions to methods."""
    code_menu = self.menuBar().addMenu('&Code')
    render_menu = self.menuBar().addMenu('&Render')
    self.menuBar().addAction('&Help', self.openHelpUrl)

    code_menu.addAction('&New', self.new).setShortcut('Ctrl+N')
    code_menu.addAction('&Open...', self.showOpen).setShortcut('Ctrl+O')
    code_menu.addAction('&Save', self.save).setShortcut('Ctrl+S')
    code_menu.addAction('Save as...', self.showSave).setShortcut('Ctrl+Shift+S')

    self.live_preview_action = render_menu.addAction('&Live Editing')
    self.live_preview_action.setCheckable(True)
    self.live_preview_action.setShortcut('Ctrl+L')
    self.connect(self.live_preview_action,
                 QtCore.SIGNAL('toggled(bool)'),
                 self.toggleLivePreview)

    self.delayed_preview_action = render_menu.addAction('&Delayed Editing')
    self.delayed_preview_action.setCheckable(True)
    self.delayed_preview_action.setShortcut('Ctrl+D')
    self.connect(self.delayed_preview_action,
                 QtCore.SIGNAL('toggled(bool)'),
                 self.toggleDelayedPreview)

    # These are circularly-dependent. Make sure both are created.
    self.live_preview_action.setChecked(True)
    self.delayed_preview_action.setChecked(False)

    render_menu.addAction('&Refresh', self.drawPreview).setShortcut('Ctrl+R')

    self.export_action = render_menu.addAction('&Export...', self.showExport)
    self.export_action.setShortcut('Ctrl+E')
    self.export_action.setEnabled(False)

    self.print_action = render_menu.addAction('&Print...', self.showPrint)
    self.print_action.setShortcut('Ctrl+P')
    self.print_action.setEnabled(False)

  def setupEditor(self):
    """Creates the editor with accessories and sets it as a centeral widget."""
    self.font = QtGui.QFont()
    self.font.setFamily('Consolas')
    self.font.setFixedPitch(True)
    self.font.setPointSize(11)
    self.font.setStyleHint(QtGui.QFont.TypeWriter)

    self.editor = TabbedTextEdit()
    self.editor.setFont(self.font)
    self.editor.setLineWrapMode(QtGui.QTextEdit.NoWrap)
    self.editor.setAcceptRichText(False)

    self.error_selection = QtGui.QTextEdit.ExtraSelection()
    self.error_selection.format = QtGui.QTextCharFormat()
    self.error_selection.format.setBackground(ERROR_BACKGROUND)
    self.error_selection.format.setProperty(
        QtGui.QTextFormat.FullWidthSelection, True)
    self.error_selection.cursor = self.editor.textCursor()

    self.highlighter = Highlighter(self.editor)

    self.setCentralWidget(self.editor)
    text_changed = QtCore.SIGNAL('textChanged()')
    self.connect(self.editor, text_changed, self.markUnsaved)
    self.connect(self.editor, text_changed, self.drawAutoPreview)
    self.connect(self.editor, QtCore.SIGNAL('keyPressed()'), self.recordAction)

  def setupCanvas(self):
    """Creates the preview dock with a diagram drawing canvas."""
    self.canvas = Canvas()
    self.dock = QtGui.QDockWidget('Diagram Preview')
    self.dock.setWidget(self.canvas)
    self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.dock)

  def setupSize(self):
    """Centers the main window and resize the dock to 45% width."""
    screen = QtGui.QDesktopWidget().availableGeometry()

    self.resize(screen.width() * 0.66, screen.height() * 0.75)

    size = self.geometry()
    self.move((screen.width() - size.width()) / 2,
              (screen.height() - size.height()) / 2)

    self.canvas.resize(size.width() * 0.45, size.height())

  def new(self):
    """Clears the editor and diagram dock for a new document.

    Verifies that all unsaved changes are saved or can be discarded via
    isSafeToReset().
    """
    if self.isSafeToReset():
      self.filepath = None
      self.editor.clear()
      self.markSaved()
      self.canvas.loadDiagram(None)

  def showOpen(self):
    """Shows the file opening dialog.

    Verifies that all unsaved changes are saved or can be discarded via
    isSafeToReset().
    """
    if self.isSafeToReset():
      filepath = QtGui.QFileDialog.getOpenFileName(
          self, 'Open File', '', 'DrawTime Code (*.dt);;All Files (*.*)')

      if filepath:
        self.open(filepath)

  def open(self, filepath):
    """Loads a diagram description file.

    Args:
      filepath: The path to the diagram description file to load.
    """
    self.filepath = filepath
    with open(filepath, encoding='utf8') as infile:
      code = infile.read().replace('\t',  '  ')
      self.editor.setPlainText(code)
      self.markSaved()
      self.drawPreview()

  def showSave(self):
    """Shows a file dialog and saves the current file to the selected path."""
    filepath = QtGui.QFileDialog.getSaveFileName(
        self, 'Save File', '', 'DrawTime Code (*.dt);;All Files (*.*)')

    if filepath:
      self.filepath = filepath
      self.save()

  def save(self):
    """Saves the current diagram description file.

    If the current file is not associated with a path (when created by
    new()), shows a file save dialog and saves only if a file is selected in it.
    """
    if self.filepath:
      with open(self.filepath, 'w', encoding='utf8') as outfile:
        outfile.write(self.editor.toPlainText())
        self.markSaved()
    else:
      self.showSave()

  def toggleLivePreview(self, is_on):
    """Toggles live preview (delayed preview is alwas disabled).

    Args:
      is_on: Whether live preview is on.
    """
    if is_on:
      self.delayed_preview_action.setChecked(False)
      self.preview_mode = PREVIEW_INSTANT
    elif self.preview_mode == PREVIEW_INSTANT:
      self.preview_mode = PREVIEW_MANUAL

  def toggleDelayedPreview(self, is_on):
    """Toggles delayed preview (live preview is alwas disabled).

    Args:
      is_on: Whether delayed preview is on.
    """
    if is_on:
      self.live_preview_action.setChecked(False)
      self.preview_mode = PREVIEW_DELAYED
      self.preview_timer = self.startTimer(PREVIEW_TIMER_RESOLUTION)
    elif self.preview_mode == PREVIEW_DELAYED:
      self.preview_mode = PREVIEW_MANUAL
      if self.preview_timer:
        self.killTimer(self.preview_timer)

  def drawAutoPreview(self):
    """Calls drawPreview() if preview mode is auto."""
    if self.preview_mode == PREVIEW_INSTANT:
      self.drawPreview()

  def drawPreview(self):
    """Parses and draws the current diagram.

    Errors are reported via reportDiagramError() and clearDiagramError().
    """
    if self.dock.isHidden():
      self.dock.show()

    self.export_action.setEnabled(False)
    self.print_action.setEnabled(False)
    
    try:
      diagram = parse.parseTimingDescription(self.editor.toPlainText())
    except parse.TimingSyntaxError as e:
      self.reportDiagramError(e)
    else:
      try:
        self.canvas.loadDiagram(diagram)
        self.canvas.repaint()
      except Exception as e:
        self.canvas.loadDiagram(None)
        self.statusBar().showMessage('Render error: {}.'.format(e))
      else:
        self.export_action.setEnabled(True)
        self.print_action.setEnabled(True)
        self.clearDiagramError()

  def reportDiagramError(self, e):
    """Highlights an error line and shows the error message in the status bar.

    Args:
      e: A parse.TimingSyntaxError exception describing the encountered error.
    """
    self.statusBar().showMessage('Error: ' + e.message)

    self.error_selection.cursor.setPosition(0)
    self.error_selection.cursor.movePosition(
        QtGui.QTextCursor.Down, QtGui.QTextCursor.MoveAnchor, e.line_number - 1)
    self.error_selection.cursor.movePosition(
        QtGui.QTextCursor.Down, QtGui.QTextCursor.KeepAnchor)
    self.editor.setExtraSelections([self.error_selection])

  def clearDiagramError(self):
    """Unhighlights the error line (if needed) and clears the status bar."""
    self.statusBar().clearMessage()
    self.editor.setExtraSelections([])

  def showExport(self):
    """Shows a file dialog and saves the rendered image to the selected path."""
    supported_formats = QtGui.QImageWriter.supportedImageFormats()
    supported_formats = [str(i, encoding='utf8') for i in supported_formats]
    supported_formats = ['{} Image (*.{})'.format(i.upper(),  i)
                         for i in supported_formats]
    filter = ';;'.join(supported_formats)
    path = QtGui.QFileDialog.getSaveFileName(self, 'Save Diagram', '', filter)

    if path:
      self.canvas.renderer.save(path)

  def showPrint(self):
    """Shows a printer selection dialog and prints the rendered image."""
    printer = QtGui.QPrinter()
    dialog = QtGui.QPrintDialog(printer, self)
    dialog.setWindowTitle('Print Diagram')
    result = dialog.exec()
    if result == QtGui.QDialog.Accepted:
      painter = QtGui.QPainter()
      is_printer_working = painter.begin(printer)
      if is_printer_working:
        painter.drawImage(printer.pageRect().topLeft(),
                          self.canvas.renderer.image)
        painter.end()
      else:
        QtGui.QMessageBox.information(
            self, 'Printing Failed',
            'Could not print to the selected printer. Please verify that the '
            'printer is operational and try again.')

  def openHelpUrl(self):
    """Opens HELP_URL in the default browser."""
    QtGui.QDesktopServices.openUrl(QtCore.QUrl(HELP_URL))

  def markSaved(self):
    """Marks the current file as saved and updates the window title."""
    self.saved = True
    self.setWindowFilePath(self.filepath or 'Untitled')
    self.setWindowModified(False)

  def markUnsaved(self):
    """Marks the current file as *not* saved and updates the window title."""
    self.saved = False
    self.setWindowModified(True)

  def isSafeToReset(self):
    """Verifies that the current file is saved or can be discarded.

    If the current file is saved, instantly returns True. Otherwise asks the
    user whether the file should be saved or can be discarded. If the user
    decides to save the file, calls save() and returns whether the file was
    saved. If the user decides to discard the file, returns True. Finally, if
    the user selects Cancel, returns False.

    Returns:
      A boolean indicating whether it is safe to unload the current file.
    """
    if not self.saved:
      message_box = QtGui.QMessageBox()
      message_box.setText('The document has been modified.')
      message_box.setInformativeText('Do you want to save your changes?')
      message_box.setStandardButtons(QtGui.QMessageBox.Save |
                                     QtGui.QMessageBox.Discard |
                                     QtGui.QMessageBox.Cancel)
      message_box.setDefaultButton(QtGui.QMessageBox.Save)
      choice = message_box.exec()

      if choice == QtGui.QMessageBox.Save:
        self.save()
      elif choice == QtGui.QMessageBox.Discard:
        return True
    return self.saved

  def recordAction(self):
    """Records the fact that an action occurred that can delay a preview."""
    self.last_action_time = time.time()

  def timerEvent(self, _):
    """Calls drawPreview() if preview mode is delayed and the delay has passed.

    Compares the current time to self.last_action_time and draws the preview if
    it the difference is above PREVIEW_DELAYED. self.last_action_time is reset
    to None on drawing.
    """
    if self.preview_mode == PREVIEW_DELAYED and self.last_action_time:
      current_time = time.time()
      if current_time - self.last_action_time >= PREVIEW_DELAY:
        self.drawPreview()
        self.last_action_time = None

  def keyPressEvent(self, event):
    """Triggers window closing when the user presses Escape."""
    if event.key() == QtCore.Qt.Key_Escape:
      self.close()

  def closeEvent(self, event):
    """Ensures that on exit the current file is saved or can be discarded."""
    if self.isSafeToReset():
      event.accept()
    else:
      event.ignore()


class TabbedTextEdit(QtGui.QTextEdit):
  """A QTextEdit that handles tabs as spaces and follows indents."""

  def keyPressEvent(self, event):
    """Intercepts Tab and Enter key presses.

    Pressing the tab key always inserts two spaces (replacing the selection if
    any).

    Pressing the Enter or Return keys insert a new line with an indent similar
    to the current line, or larger by two spaces if the last line ended with a
    colon.

    All other keys are passed on to QTextEdit's default keyPressEvent().

    At the end of the event, emits a keyPressed() signal.
    """
    if event.key() == QtCore.Qt.Key_Tab:
      self.insertPlainText('  ')
    elif event.key() in (QtCore.Qt.Key_Enter, QtCore.Qt.Key_Return):
      cursor = self.textCursor()
      cursor.movePosition(
          QtGui.QTextCursor.StartOfLine, QtGui.QTextCursor.MoveAnchor)
      cursor.movePosition(
          QtGui.QTextCursor.EndOfLine, QtGui.QTextCursor.KeepAnchor)

      text = cursor.selectedText()
      spaces = len(text) - len(text.lstrip())
      if text.rstrip().endswith(':'):
        spaces += 2

      self.insertPlainText('\n' + ' ' * spaces)
    else:
      super().keyPressEvent(event)
    self.emit(QtCore.SIGNAL("keyPressed()"))


class Canvas(QtGui.QWidget):
  """A canvas drawn by the diagram renderer."""

  def __init__(self,  parent=None):
    super().__init__(parent)
    self.renderer = render.Renderer()

  def isEmpty(self):
    """Returns whether the canvas has a valid diagram set."""
    return self.renderer.image is not None

  def loadDiagram(self, diagram):
    """Loads a diagram into the widget.

    Args:
      diagram: A model.TimingDiagram to be rendered on the canvas.
    """
    if diagram and diagram.signals:
      self.renderer.draw(diagram)
      self.resize(self.renderer.image.size())
    else:
      self.renderer.image = None

  def paintEvent(self, event):
    """Repaints the canvas from the self.renderer.image (if initialized).

    If no diagram or an invalid diagram is loaded, draws a message indicating
    that.
    """
    painter = QtGui.QPainter(self)
    size = self.size()
    rect = QtCore.QRect(0, 0, size.width(), size.height())
    painter.fillRect(rect, QtCore.Qt.white)

    if self.renderer.image:
      dirty_rect = event.rect()
      painter.drawImage(dirty_rect, self.renderer.image, dirty_rect)
    else:
      painter.setPen(QtCore.Qt.black)
      painter.drawText(
          rect, QtCore.Qt.AlignCenter, 'No diagram or empty diagram loaded.')

    painter.end()

  def sizeHint(self):
    """Reports the canvas's size, e.g. to containers."""
    return self.size()


class Highlighter(QtGui.QSyntaxHighlighter):
  """A highlighter for the DrawTime syntax."""

  def __init__(self, parent=None):
    """Initializes syntax regexes and token styles."""
    super().__init__(parent)

    self.comment_pattern = re.compile(r'^\s*#.*$')
    self.block_pattern = re.compile(
        r'^\s*(style|time|(clock|line|bus)\s+(.+?))\s*(:)\s*$')
    self.property_pattern = re.compile(r'^\s*({})\s*(=)\s*(.+?)\s*$'.format(
        '|'.join(['width', 'height', 'margin', 'font_size', 'font_family',
                  'background', 'foreground', 'step', 'start', 'end', 'delay',
                  'length', 'offset', 'duty'])))
    self.change_pattern = re.compile(
        r'^\s*([-\d]+)\s*(->)\s*(0|1|Z|\?|"(?:[^"]|\\.)*")\s*$')

    self.block_format = QtGui.QTextCharFormat()
    self.block_format.setFontWeight(QtGui.QFont.Bold)
    self.block_format.setForeground(QtGui.QColor('#000080'))
    self.label_format = QtGui.QTextCharFormat()
    self.label_format.setForeground(QtGui.QColor('#008080'))
    self.comment_format = QtGui.QTextCharFormat()
    self.comment_format.setForeground(QtGui.QColor('#008000'))
    self.property_format = QtGui.QTextCharFormat()
    self.property_format.setForeground(QtGui.QColor('#A05000'))
    self.operator_format = QtGui.QTextCharFormat()
    self.operator_format.setForeground(QtGui.QColor('#000000'))
    self.operator_format.setFontWeight(QtGui.QFont.Bold)
    self.value_format = QtGui.QTextCharFormat()
    self.value_format.setForeground(QtGui.QColor('#800080'))
    self.time_format = QtGui.QTextCharFormat()
    self.time_format.setForeground(QtGui.QColor('#606000'))
    self.signal_format = QtGui.QTextCharFormat()
    self.signal_format.setForeground(QtGui.QColor('#800000'))

  def highlightBlock(self, text):
    """Highlights a line of DrawTime code.

    For the purposes of highlighting, each line of DrawTime code can be
    highlighted independently, and as such this method does not use the
    QSyntaxHighlighter block state management utilities.

    All highlighting is done using setFormat.

    Args:
      text: The contents of the line to highlight.
    """
    if self.comment_pattern.match(text):
      self.setFormat(0, len(text), self.comment_format)
      return

    block_line = self.block_pattern.match(text)
    if block_line:
      if block_line.group(2):
        start, end = block_line.span(2)
        self.setFormat(start, end - start, self.block_format)
        start, end = block_line.span(3)
        self.setFormat(start, end - start, self.label_format)
      else:
        start, end = block_line.span(1)
        self.setFormat(start, end - start, self.block_format)
      self.setFormat(block_line.span(4)[0], 1, self.operator_format)
      return

    property_line = self.property_pattern.match(text)
    if property_line:
      start, end = property_line.span(1)
      self.setFormat(start, end - start, self.property_format)

      self.setFormat(property_line.span(2)[0], 1, self.operator_format)

      start, end = property_line.span(3)
      self.setFormat(start, end - start, self.value_format)
      return

    change_line = self.change_pattern.match(text)
    if change_line:
      start, end = change_line.span(1)
      self.setFormat(start, end - start, self.time_format)

      self.setFormat(change_line.span(2)[0], 2, self.operator_format)

      start, end = change_line.span(3)
      self.setFormat(start, end - start, self.signal_format)
      return
