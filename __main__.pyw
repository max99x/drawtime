#!/usr/bin/python3
"""DrawTime - a tool to render timing diagrams from textual descriptions."""

import sys
from PyQt4 import QtGui
import parse
import render
import gui


def runGUI(app, filename=None):
  """Starts the editor GUI, optionally loading a diagram description.

  Args:
    app: The QApplication used to run the GUI.
    filename: An optional path of a diagram description (code) file to open.
  """
  editor = gui.Editor()
  editor.show()
  if filename:
    try:
      editor.open(filename)
    except IOError as e:
      print(e)
      sys.exit(-1)
  else:
    editor.new()
  sys.exit(app.exec_())


def runQuickRender(infile_name, outfile_name):
  """Reads a diagram description are renders it to a file, then exits.

  Args:
    infile_name: The path of a diagram description (code) file to read.
    outfile_name: The path where the rendered diagram is to be written. The
      format of the output is determined from the extension of this file. Any
      format supported by QImageWriter is supported. If the file exists, it is
      silently overwritten.
  """
  with open(infile_name, encoding='utf8') as infile:
    code = infile.read()
    diagram = parse.parseTimingDescription(code)
    renderer = render.Renderer()
    renderer.draw(diagram)
    renderer.save(outfile_name)
  sys.exit(0)


def main():
  """Decides whether to run the GUI or a simple one-off render.

  If the program is run with no arguments, or only one argument is provided, the
  editor GUI is shown, and a file is loaded in the latter case.

  However, if two arguments are provided, the first is treated as the code to
  read and the second as the path where the output is to be stored. Note that
  the output file is silently overwritten.
  """
  app = QtGui.QApplication(sys.argv)
  app.setApplicationName('DrawTime')

  if len(sys.argv) == 1:
    runGUI(app)
  elif len(sys.argv) == 2:
    runGUI(app, sys.argv[1])
  elif len(sys.argv) == 3:
    runQuickRender(*sys.argv[1:3])
  else:
    print('Usage:\npython3 drawtime [code-file [diagram-file]]')


if __name__ == '__main__':
  main()
