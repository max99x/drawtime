"""Structs to hold information about timing diagrams."""

import collections
import numbers


# An object to represent signals whose value is not known.
UNKNOWN = object()


class TimingDiagram:
  """The main timing diagram struct.

  Holds global style and timing information, as well as a list of signals (each
  a Clock, Bus or Line).

  Style properties are self-explantory, while the timing properties are as
  follows:
    start: The minimum time value displayed in the chart. For example, if start
      is set to 20, and a signal changes at time 10, it will not be shown in the
      diagram. This can be a negative value.
    end: The maximum time value displayed in the chart. For example, if end is
      set to 20, and a signal changes at time 30, it will not be shown in the
      diagram.
    step: If not None, the diagram is split into columns, each step time units
      wide, labeled with T#, where # is the column number.
    delay: The length of time it takes each signal to complete a value change.
  """

  def __init__(self,
               width = 800,
               height = 600,
               margin = 20,
               font_size = 12,
               font_family = 'Times New Roman',
               background = 0xffffff,
               foreground = 0x000000,
               start = 0,
               end = 100,
               step = None,
               delay = 10,
               signals = None):
    self.width = width
    self.height = height
    if margin > width / 2 or margin > height / 2:
      raise ValueError('The diagram margin must be less than half the width or '
                       'half the height of the diagram (whichever is less).')
    self.margin = margin
    self.font_size = font_size
    self.font_family = font_family
    self.background = background
    self.foreground = foreground
    self.start = start
    self.end = end
    self.step = step
    self.delay = delay
    self.signals = signals or []


class Line:
  """A named line signal that has a start value and a series of changes.

  The start value can be 0, 1, None (floating), or UNKNOWN.

  The changes are provided as a dictionary mapping time instants to values which
  the signal takes at those times. Values to which a line can change are 0, 1
  and None (floating).
  """

  def __init__(self, name, start, changes):
    self.name = name

    if start not in {0, 1, UNKNOWN, None}:
      raise TypeError('The start value must be one of:{0, 1, UNKNOWN, None}. '
                      'Got {}.'.format(repr(start)))
    self.start = start

    self.changes = collections.OrderedDict()
    for time, value in sorted(changes.items()):
      if not isinstance(time, numbers.Number):
        raise TypeError('A line change time must be a number. '
                        'Got {}'.format(repr(time)))
      elif value not in {0, 1, None}:
        raise TypeError('A line change value must be be one of: {0, 1, None}. '
                        'Got {}.'.format(repr(value)))
      elif time in self.changes:
        raise ValueError('Duplicate line change time: {}'.format(time))

      self.changes[time] = value


class Bus:
  """A named bus signal that has start value and a series of changes.

  The start value can be UNKNOWN, None (floating) or an arbitrary string.

  The changes are provided as a dictionary mapping time instants to values which
  the signal takes at those times. Values to which a buscan change are UNKNOWN,
  None (floating) and arbitrary strings.
  """

  def __init__(self, name, start, changes):
    self.name = name
    self.start = start
    self.changes = collections.OrderedDict()
    for time, value in sorted(changes.items()):
      if not isinstance(time, numbers.Number):
        raise TypeError('A line change time must be a number. '
                        'Got {}'.format(repr(time)))
      elif time in self.changes:
        raise ValueError('Duplicate line change time: {}'.format(time))

      self.changes[time] = value


class Clock:
  """A named clock signal that follows a regular pattern.

  A clock is defined by the length of its cycle, its duty cycle (how long it is
  in the 1 position per cycle), and an offset from which the signal starts.
  """

  def __init__(self, name, offset, length, duty):
    self.name = name
    self.offset = offset
    self.length = length
    if not 0 < duty < 1:
      raise ValueError('Clock duty cycle must be within (0, 1) exclusive.')
    self.duty = duty
