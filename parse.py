"""A parser for DrawTime timing diagram descriptions."""

import ast
import model
import re


# Error messages for various syntax errors.
ERRORS = {
  'time_args': 'A time block must have no arguments.',
  'style_args': 'A style block must have no arguments.',
  'unknown_block': ('Unknown block type. Valid types are '
                    '"time", "style", "clock X", "bus X" and "line X".'),
  'orphan_colon': 'A colon encountered without a block keyword.',
  'orphan_line': 'A property or change line encountered outside of a block.',
  'signal_args': 'A signal block must have a name argument.',
  'malformed_line': 'Malformed line.',
  'time_prop': 'Unknown time property.',
  'style_prop': 'Unknown style property.',
  'signal_prop': 'Unknown signal propery.',
  'bad_float': 'The specified property value is not a valid number.',
  'bad_int': 'The specified property value is not a valid integer.',
  'bad_color': ('The specified property value is not a valid color. '
                'Colors must be in the RRGGBB format.'),
  'clock_change': 'Clock signals do not support change commands.',
  'line_value': ('Invalid signal value for a line signal. Accepted values are '
                 '0, 1, Z (float) and ? (unknown).'),
  'bus_value': ('Invalid signal value for a bus signal. Accepted values are '
                'Z (float), ? (unknown) or a quoted string.'),
  'line_unknown': 'Line signals cannot change to the "unknown" state.',
  'change_dupe': 'Duplicate signal change time.',
  'missing_prop': ('A signal does not have all its properties defined. '
                   'Clock signals must have offset, length and duty specified. '
                   'Bus and line signals must have a start value specified.'),
  'empty_block': 'An empty block encountered.'
}

# Properties allowed in the time block.
TIME_PROPERTIES = {'start', 'end', 'step', 'delay'}

# Properties allowed in the style block, along with their types.
STYLE_PROPERTIES = {
  'width': 'number',
  'height': 'number',
  'margin': 'number',
  'font_size': 'number',
  'font_family': 'string',
  'background': 'color',
  'foreground': 'color'
}

# A regular expression used to validate color values.
COLOR_REGEX = re.compile(r'^[0-9a-f]{6}$', re.IGNORECASE)

# Properties allowed in each type of signal blocks.
SIGNAL_PROPERTIES = {
  'clock': {'length', 'offset', 'duty'},
  'line': {'start'},
  'bus': {'start'}
}

# Recognized types of signal blocks, mapped to the structs that can hold them.
SIGNAL_TYPES = {
  'clock': model.Clock,
  'line': model.Line,
  'bus': model.Bus
}


class TimingSyntaxError(ValueError):
  """A syntax error encountered while parsing a timing diagram description.

  When raised, takes an error type (a key into ERRORS) and a tuple containing
  the number and contents of the line where the error occurred.
  """

  def __init__(self, error_type, numbered_line):
    self.message = ERRORS[error_type]
    self.line_number, self.line = numbered_line
    formatted = '{}\nLine {}: {}'.format(self.message, *numbered_line)
    super().__init__(formatted)


def parseTimingDescription(code):
  """Parses diagram description code and constructs a diagram object.

  Args:
    code: A string containing the raw diagram description code.

  Returns:
    A model.TimingDiagram represented by the supplied code.
  """
  lines = [i.strip() for i in code.splitlines()]
  numbered_lines = [(number + 1, line)
                    for number, line in enumerate(lines)
                    if line and not line.startswith('#')]
  return _parseBlocks(*_exractBlocks(numbered_lines))


def _exractBlocks(numbered_lines):
  """Groups code lines into time, style and signal blocks.

  Args:
    numbered_lines: A list of tuples, each containing a line number and its
      text. Line numbers are used solely for error reporting.

  Returns:
    A triple containing:
      1. The time block, a list of numbered lines from the input that were
         contained in the time code block.
      2. The style block, a list of numbered lines from the input that were
         contained in the style code block.
      3. A list of signal blocks. Each block a tuple containing the signal type,
         its name, and a list of numbered lines from the input.
  """
  time_lines = []
  style_lines = []
  signal_blocks = []
  current_block = None

  for numbered_line in numbered_lines:
    number, line = numbered_line
    if line.endswith(':'):
      if current_block == []:
        raise TimingSyntaxError('empty_block', numbered_line)
      if len(line) == 1:
        raise TimingSyntaxError('orphan_colon', numbered_line)
      block_type, *block_args = line[:-1].split(None, 1)

      if block_type == 'time':
        if block_args:
          raise TimingSyntaxError('time_args', numbered_line)
        current_block = time_lines
      elif block_type == 'style':
        if block_args:
          raise TimingSyntaxError('style_args', numbered_line)
        current_block = style_lines
      elif block_type in ('clock', 'line', 'bus'):
        if not block_args:
          raise TimingSyntaxError('signal_args', numbered_line)
        current_block = []
        signal_blocks.append((block_type, block_args[0], current_block))
      else:
        raise TimingSyntaxError('unknown_block', numbered_line)
    else:
      if current_block is None:
        raise TimingSyntaxError('orphan_line', numbered_line)
      current_block.append(numbered_line)

  if current_block == []:
    raise TimingSyntaxError('empty_block', numbered_line)

  return time_lines, style_lines, signal_blocks


def _parseBlocks(time_lines, style_lines, signal_blocks):
  """Semantically parses code blocks and assembles a diagram object.

  Args:
    time_lines: A list of numbered lines contained in the time block.
    style_lines: A list of numbered lines contained in the style block.
    signal_blocks: A list of signal blocks. Each block a tuple containing the
      signal type, its name, and a list of numbered lines from the input.

  Returns:
    A model.TimingDiagram represented by the supplied blocks.
  """
  diagram = model.TimingDiagram()

  for number, line in style_lines:
    property, _, value = _splitLine(number, line)
    if property not in STYLE_PROPERTIES:
      raise TimingSyntaxError('style_prop', (number, line))
    property_type = STYLE_PROPERTIES[property]

    if property_type == 'number':
      value = _parseInt(value, number, line)
    elif property_type == 'color':
      if not COLOR_REGEX.match(value):
        raise TimingSyntaxError('bad_color', (number, line))
      value = int(value, 16)

    setattr(diagram, property, value)

  for number, line in time_lines:
    property, _, value = _splitLine(number, line)
    if property not in TIME_PROPERTIES:
      raise TimingSyntaxError('time_prop', (number, line))
    setattr(diagram, property, _parseInt(value, number, line))

  for signal_type, signal_name, signal_lines in signal_blocks:
    properties = {}
    changes = {}

    for number, line in signal_lines:
      target, operation, value = _splitLine(number, line, True)
      if operation == '->':
        if signal_type == 'clock':
          raise TimingSyntaxError('clock_change', (number, line))

        time = _parseFloat(target, number, line)
        if time in changes:
          raise TimingSyntaxError('change_dupe', (number, line))

        value = _parseSignalValue(value, signal_type, number, line)
        if signal_type == 'line' and value == model.UNKNOWN:
          raise TimingSyntaxError('line_unknown', (number, line))

        changes[time] = value
      else:
        if target not in SIGNAL_PROPERTIES[signal_type]:
          raise TimingSyntaxError('signal_prop', (number, line))

        if target == 'start':
          properties[target] = _parseSignalValue(
              value, signal_type, number, line)
        else:
          properties[target] = _parseFloat(value, number, line)

    if not properties.keys() == SIGNAL_PROPERTIES[signal_type]:
      raise TimingSyntaxError('missing_prop', signal_lines[-1])

    if signal_type != 'clock':
      properties['changes'] = changes

    diagram.signals.append(SIGNAL_TYPES[signal_type](signal_name, **properties))

  return diagram


def _splitLine(line_number, line, allow_change=False):
  """Splits a property or change line.

  Args:
    line_number: The number of the line being split. Used for error reporting.
    line: The string to split.
    allow_change: If True, both -> and = operators are taken into account.
      Otherwise only = is used.

  Returns:
    A triple containing the LHS, operator and RHS. LHS and RHS have all extrnal
    space trimmed.
  """
  delimiter = '->' if (allow_change and '->' in line) else '='
  if delimiter not in line:
    raise TimingSyntaxError('malformed_line', (line_number, line))
  return map(str.strip, line.partition(delimiter))


def _parseFloat(raw, line_number, line_text):
  """Parses a float from a string with standard error reporting.

  Args:
    raw: The string to parse.
    line_number: The number of the current line, used for error reporting.
    line_text: The contents of the current line, used for error reporting.

  Returns:
    The float represented by raw.
  """
  return _parseNumber(raw, float, line_number, line_text)


def _parseInt(raw, line_number, line_text):
  """Parses an integer from a string with standard error reporting.

  Args:
    raw: The string to parse.
    line_number: The number of the current line, used for error reporting.
    line_text: The contents of the current line, used for error reporting.

  Returns:
    The integer represented by raw.
  """
  return _parseNumber(raw, int, line_number, line_text)


def _parseNumber(raw, type, line_number, line_text):
  """Parses a number from a string with standard error reporting.

  Args:
    raw: The string to parse.
    type: The type constructor to use, e.g. int, float.
    line_number: The number of the current line, used for error reporting.
    line_text: The contents of the current line, used for error reporting.

  Returns:
    The number represented by raw, of the specified type.
  """
  try:
    return type(raw)
  except ValueError:
    raise TimingSyntaxError('bad_' + type.__name__, (line_number, line_text))


def _parseSignalValue(value, signal_type, line_number, line_text):
  """Parses and validates a signal value.

  Args:
    value: The string to parse.
    signal_type: The type of the signal: clock, line or bus.
    line_number: The number of the current line, used for error reporting.
    line_text: The contents of the current line, used for error reporting.

  Returns:
    The value parsed and cast to the appropriate type.
  """
  if signal_type == 'line':
    if value in {'1', '0'}:
      return int(value)
    elif value == 'Z':
      return None
    elif value == '?':
      return model.UNKNOWN
    else:
      raise TimingSyntaxError('line_value', (line_number, line_text))
  elif signal_type == 'bus':
    if value == 'Z':
      return None
    elif value == '?':
      return model.UNKNOWN
    else:
      try:
        value = ast.literal_eval(value)
        if not isinstance(value, str):
          raise TimingSyntaxError('bus_value', (line_number, line_text))
        return value
      except SyntaxError:
        raise TimingSyntaxError('bus_value', (line_number, line_text))
  else:
    raise ValueError('Invalid signal type: ' + signal_type)
