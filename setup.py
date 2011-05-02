"""A distutils script to build DrawTime on Windows.

Build into an exe with:
  python3 setup.py build
Build into an installer with:
  python3 setup.py bdist_msi
"""

from cx_Freeze import setup, Executable


if __name__ == '__main__':
  exe = Executable(script='__main__.pyw',
                   base='Win32GUI',
                   targetName='DrawTime.exe',
                   icon='data/drawtime.ico',
                   copyDependentFiles=True,
                   shortcutDir='ProgramMenuFolder',
                   shortcutName='DrawTime')
  setup(name='DrawTime',
        version='1.0',
        author='Max Shawabkeh',
        description='An editor for timing diagrams.',
        executables=[exe],
        data_files=[('', ['LICENSE', 'README']),
                    ('data', ['data/drawtime.png', 'data/example.dt'])])
