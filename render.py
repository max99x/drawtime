"""A Qt renderer for timing diagrams."""

import re
from PyQt4 import QtGui,  QtCore
import model


# The height of text rectangles, relative to font height.
TEXT_HEIGHT = 1.2

# The color of the background of bus segments representing unknown values.
UNKNOWN_BACKGROUND = QtCore.Qt.gray


class Renderer:
  """A Qt-based renderer for timing diagrams."""

  def __init__(self):
    self.image = None
    self.painter = QtGui.QPainter()

  def save(self, filepath):
    """Saves the last drawn diagram to an image file.

    This can be called only after a successful call to Renderer.draw().

    Args:
      filepath: The path to which the image is to be saved. The format of the
        image is guessed from the extension. If the file already exists, it is
        silently overwritten.
    """
    if self.image:
      result = self.image.save(filepath)
      if not result:
        raise IOError('Failed to save image.')
    else:
      raise RuntimeError('No diagram loaded.')

  def draw(self, diagram):
    """Draws the specified diagram, saving the result to self.image.

    Args:
      diagram: The diagram to draw.
    """
    if not diagram:
      raise ValueError('No diagram provided.')

    self._loadDiagram(diagram)

    self.painter.begin(self.image)
    try:
      self.painter.setFont(self._font)
      self.painter.setRenderHint(QtGui.QPainter.TextAntialiasing)

      self.painter.fillRect(
          QtCore.QRect(QtCore.QPoint(0, 0), self.image.size()), self._background)
      self._drawFrame()
      self._drawSignals()
    finally:
      self.painter.end()

  def _loadDiagram(self, diagram):
    """Fills data members with properties calculated from a diagram.

    Used to initialize global diagram setting used by drawing methods.

    Args:
      diagram: The diagram to load.
    """
    self.image = QtGui.QImage(
        diagram.width, diagram.height, QtGui.QImage.Format_ARGB32)

    self._font = QtGui.QFont(diagram.font_family, diagram.font_size)

    self._diagram = diagram
    self._background = QtGui.QColor('#' + hex(diagram.background)[2:].zfill(6))
    self._color = QtGui.QColor('#' + hex(diagram.foreground)[2:].zfill(6))

    margin = diagram.margin
    self._outer_frame = QtCore.QRectF(
        margin, margin, diagram.width - 2 * margin, diagram.height - 2 * margin)

    label_widths = [self._getTextWidth(i.name + '  ') for i in diagram.signals]
    assert len(label_widths) > 0, 'A diagram must have at least one signal.'
    self._inner_frame = QtCore.QRectF(
        margin + max(label_widths),
        margin + self._getTextHeight() * TEXT_HEIGHT,
        self._outer_frame.width() - max(label_widths),
        self._outer_frame.height() - self._getTextHeight() * TEXT_HEIGHT)

  def _drawFrame(self):
    """Draws the frame surrounding the loaded diagram.

    If the diagram defines a step length, also draws and labels the columns into
    which the diagram is divided.
    """
    old_pen = self.painter.pen()
    self.painter.setPen(QtGui.QPen(self._color))
    self.painter.drawRect(self._outer_frame)
    self.painter.drawRect(self._inner_frame)
    self.painter.setPen(old_pen)

    if self._diagram.step:
      width = self._diagram.end - self._diagram.start
      pixels_per_unit = self._inner_frame.width() / width
      pixels_per_step = pixels_per_unit * self._diagram.step
      stops = [self._timeToPixels(i)
               for i in range(0, self._diagram.end, self._diagram.step)]
      for index, left in enumerate(stops):
        self._drawLine(left, self._inner_frame.top() + 1,
                       left, self._inner_frame.bottom(),
                       dashed=True)
        if index != len(stops) - 1:
          center_x = left + pixels_per_step / 2
          center_y = self._inner_frame.top() - self._getTextHeight() * 0.5
          self._drawText('T{}'.format(index + 1), center_x, center_y)

  def _drawSignals(self):
    """Draws the signals defined in the loaded diagram, in order."""
    frame = self._inner_frame.translated(0, 0)  # Copy.
    frame.setHeight(frame.height() / len(self._diagram.signals))
    for signal in self._diagram.signals:
      if isinstance(signal, model.Clock):
        signal = self._clockToLine(signal)

      if isinstance(signal, model.Line):
        self._drawLineSignal(signal, frame)
      elif isinstance(signal, model.Bus):
        self._drawBusSignal(signal, frame)
      else:
        raise TypeError('Invalid signal type: {}'.format(type(signal)))

      self._drawText(signal.name,
                     frame.left() - self._getTextWidth(signal.name + '  ') / 2,
                     (frame.top() + frame.bottom()) / 2)

      frame.moveTop(frame.top() + frame.height())

  def _drawBusSignal(self, bus, frame):
    """Draws a bus signal in the specified frame.

    Args:
      bus: The model.Bus to draw.
      frame: The QRect where the signal is to be drawn.
    """
    diagram = self._diagram

    high = frame.top() + frame.height() * 0.3
    middle = frame.top() + frame.height() * 0.5
    low = frame.top() + frame.height() * 0.7
    margin = self._timeDeltaToPixels(diagram.delay / 2)

    changes = bus.changes.copy()
    if changes:
      last_time, last_value = changes.popitem()
      changes[last_time] = last_value
      if last_time < diagram.end:
        changes[diagram.end] = last_value
    else:
      changes[diagram.end] = bus.start

    last = (self._timeToPixels(diagram.start), bus.start)
    for next_time, next_value in changes.items():
      x, value = last
      next_x = min(frame.right() - 1, self._timeToPixels(next_time)) + margin
      if value is None:
        self._drawLine(x + 1, middle, min(frame.right() - 1, next_x), middle, 2)
      else:
        points = [(x + margin, low),
                  (x + margin, high)]
        if x > frame.left():
          points.insert(1, (x + 1, middle))
        else:
          points.insert(1, (x + 1, low))
          points.insert(2, (x + 1, high))
        if next_x - margin < frame.right() - 1:
          points += [(next_x - margin, high),
                     (next_x, middle),
                     (next_x - margin, low)]
        else:
          points += [(next_x - margin - 1, high),
                     (next_x - margin - 1, low)]
        points = [QtCore.QPointF(*i) for i in points]

        old_pen = self.painter.pen()
        old_brush = self.painter.brush()
        self.painter.setPen(QtCore.Qt.NoPen)
        self.painter.setRenderHint(QtGui.QPainter.Antialiasing)

        if value is model.UNKNOWN:
          self.painter.setBrush(QtGui.QBrush(UNKNOWN_BACKGROUND))
          self.painter.drawConvexPolygon(*points)
        elif isinstance(value, str):
          self.painter.setBrush(QtGui.QBrush(self._background))
          self.painter.drawConvexPolygon(*points)
        else:
          raise TypeError('Invalid bus value: {}'.format(value))

        self.painter.setPen(old_pen)
        self.painter.setBrush(old_brush)
        self.painter.setRenderHint(QtGui.QPainter.Antialiasing, False)

        if isinstance(value, str):
          center_x = (x + next_x + margin) / 2
          top_margin = self._getTextHeight() * (TEXT_HEIGHT - 1) / 2
          center_y = frame.center().y() - top_margin
          self._drawText(value, center_x, center_y, ignore_markup=True)

        if x > frame.left():
          self._drawLine(x, middle, x + margin, high, 2)
          self._drawLine(x, middle, x + margin, low, 2)
        else:
          self._drawLine(x + 1, high, x + margin, high, 2)
          self._drawLine(x + 1, low, x + margin, low, 2)

        self._drawLine(x + margin + 1, high, next_x - margin, high, 2)
        self._drawLine(x + margin + 1, low, next_x - margin, low, 2)

        if next_x - margin < frame.right() - 1:
          self._drawLine(next_x - margin, high, next_x, middle, 2)
          self._drawLine(next_x - margin, low, next_x, middle, 2)
      last = (next_x, next_value)

  def _drawLineSignal(self, line, frame):
    """Draws a line signal in the specified frame.

    Args:
      line: The model.Line to draw.
      frame: The QRect where the signal is to be drawn.
    """
    diagram = self._diagram

    levels = {
      1: frame.top() + frame.height() * 0.3,
      None: frame.top() + frame.height() * 0.5,
      0: frame.top() + frame.height() * 0.7
    }

    if line.changes:
      changes = line.changes.copy()
      last_time, last_value = changes.popitem()
      changes[last_time] = last_value
      if last_time < diagram.end:
        changes[diagram.end + diagram.delay / 2] = last_value
    else:
      changes = {diagram.end + diagram.delay / 2: line.start}

    last = (diagram.start - diagram.delay / 2, line.start)
    for time, value in changes.items():
      last_time, last_value = last
      last_x = self._timeToPixels(last_time)
      time += diagram.delay / 2
      x = self._timeToPixels(time)
      x_minus_delay = self._timeToPixels(time - diagram.delay)
      if last_value == model.UNKNOWN:
        self._drawLine(last_x + 1, levels[0], x_minus_delay, levels[0], 2)
        self._drawLine(last_x + 1, levels[1], x_minus_delay, levels[1], 2)
        self._drawLine(x_minus_delay, levels[0], x, levels[value], 2)
        self._drawLine(x_minus_delay, levels[1], x, levels[value], 2)
      elif value == last_value:
        self._drawLine(last_x + 1, levels[value], x, levels[value], 2)
      else:
        self._drawLine(last_x + 1, levels[last_value],
                       x_minus_delay, levels[last_value],
                       2)
        self._drawLine(x_minus_delay, levels[last_value],
                       x, levels[value],
                       2)
      last = (time, value)

  def _drawLine(self, x1, y1, x2, y2, width=1, dashed=False):
    """Draws a line between the two specified points.

    If the line is slanted (neither horizontal nor vertical) it is drawn with
    anti-aliasing enabled.

    Args:
      x1: The X coordinate of the first point.
      y1: The Y coordinate of the first point.
      x2: The X coordinate of the second point.
      y2: The Y coordinate of the second point.
      width: The width of the line.
      dashed: If True, the line is drawn using a dashed style.
    """
    old_pen = self.painter.pen()

    self.painter.setRenderHint(QtGui.QPainter.Antialiasing,
                               x1 != x2 and y1 != y2)

    new_pen = QtGui.QPen(self._color)
    new_pen.setWidth(width)
    if dashed:
      new_pen.setStyle(QtCore.Qt.CustomDashLine)
      new_pen.setDashPattern([4, 4])
    else:
      new_pen.setStyle(QtCore.Qt.SolidLine)

    self.painter.setPen(new_pen)
    self.painter.drawLine(x1, y1, x2, y2)

    self.painter.setPen(old_pen)
    self.painter.setRenderHint(QtGui.QPainter.Antialiasing, False)

  def _drawText(self, text, center_x, center_y, ignore_markup=False):
    """Draws the specified text at a specified point.

    Args:
      text: The text to draw. If ignore_markup is False, this text is parsed for
        markup. If the text begins with an exclamation mark (!), a line will be
        drawn above it. To draw the line only over part of the text, separate
        the two parts by a forward slash (/) and prepend the one which is to
        have a line drawn above it by an exclamation mark (!). Examples:
          !ABCD -> will draw ABCD with a line over all of it.
          AB!CD -> will draw AB!CD without any lines.
          !AB/CD -> will draw AB/CD with a line over AB.
          AB/!CD -> will draw AB/CD with a line over CD.
          !AB/!CD -> will draw AB/CD with a line over both AB and CD
          !AB/!CD/!EF -> will draw AB/CD/!EF with a line over AB and CD.
      center_x: The X coordinate of the center of the text.
      center_x: The Y coordinate of the center of the text.
      ignore_markup: If True, the text is drawn as-is without any omissions or
        extra lines.
    """
    if ignore_markup:
      clean_text = text
    else:
      clean_text = re.sub('(^|/)!', r'\1', text)

    alignment = QtCore.Qt.TextSingleLine | QtCore.Qt.AlignCenter
    metrics = self.painter.fontMetrics()
    width = metrics.width(clean_text)
    height = metrics.height()
    rect = QtCore.QRectF(
        center_x - width / 2, center_y - height / 2, width, height)

    if ignore_markup:
      self.painter.drawText(rect, alignment, text)
    else:
      for part in text.partition('/'):
        overline = part.startswith('!')
        if overline: part = part[1:]

        rect.setWidth(metrics.width(part))
        self.painter.drawText(rect, alignment, part)
        if overline:
          self._drawLine(rect.left(), rect.top(), rect.right(), rect.top())
        rect.moveLeft(rect.right())

  def _timeToPixels(self, time):
    """Converts a time instant to an X coordinate on the diagram image.

    Args:
      time: The time to convert.

    Returns:
      The absolute X coordinate on the diagram image corresponding to the
      specified time.
    """
    offset = max(0, self._timeDeltaToPixels(time - self._diagram.start))
    return min(self._inner_frame.right() - 1, self._inner_frame.left() + offset)

  def _timeDeltaToPixels(self, time):
    """Converts a time delta to a horizontal distance on the diagram image.

    Args:
      time: The time delta to convert.

    Returns:
      The horizontal distance represented by the specified time delta, in pixels
      on the diagram image.
    """
    total_time = self._diagram.end - self._diagram.start
    pixels_per_time_unit = self._inner_frame.width() / total_time
    return time * pixels_per_time_unit

  def _getTextWidth(self, text, strip_markup=True):
    """Calculates the width of a given text string with the current font.

    Args:
      text: The text to measure.
      strip_markup: If true, removes markup from the specified text before
        measuring.

    Returns:
      The width of the text, in pixels.
    """
    if strip_markup:
      text = re.sub('(^|/)!', r'\1', text)
    return QtGui.QFontMetrics(self._font).width(text)

  def _getTextHeight(self):
    """Returns the height of the current font in pixels."""
    return QtGui.QFontMetrics(self._font).height()

  def _clockToLine(self, clock):
    """Converts a clock signal to a line signal for rendering.

    Calculates all the changes to the clock's value that will be visible in the
    diagram and recreates them as a line signal.

    Args:
      clock: The model.Clock to convert.

    Returns:
      A model.Line that contains all the clock changes visible within the loaded
      diagram.
    """
    on_length = clock.duty * clock.length
    off_length = clock.length - on_length
    line = model.Line(clock.name, 0, {})

    time = -(-clock.offset % clock.length)
    active = False
    while time < self._diagram.end:
      time += on_length if active else off_length
      active = not active
      if time <= self._diagram.start:
        line.start = int(active)
      else:
        line.changes[time] = int(active)

    line.changes.popitem()

    return line
