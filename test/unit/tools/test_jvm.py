import os
from unittest import mock

from .. import *

from bfg9000 import file_types, options as opts
from bfg9000.languages import Languages
from bfg9000.path import Path, Root
from bfg9000.tools.jvm import JvmBuilder
from bfg9000.versioning import Version

known_langs = Languages()
with known_langs.make('java') as x:
    x.vars(compiler='JAVAC', runner='JAVACMD', flags='JAVAFLAGS')
with known_langs.make('scala') as x:
    x.vars(compiler='SCALAC', runner='SCALACMD', flags='SCALAFLAGS')


def mock_which(*args, **kwargs):
    return ['command']


class TestJvmBuilder(CrossPlatformTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(clear_variables=True, *args, **kwargs)

    def test_properties(self):
        def mock_execute(*args, **kwargs):
            return 'version'

        with mock.patch('bfg9000.shell.which', mock_which), \
             mock.patch('bfg9000.shell.execute', mock_execute):  # noqa
            jvm = JvmBuilder(self.env, known_langs['java'], ['javac'],
                             'version')

        self.assertEqual(jvm.flavor, 'jvm')
        self.assertEqual(jvm.compiler.flavor, 'jvm')
        self.assertEqual(jvm.linker('executable').flavor, 'jar')
        self.assertEqual(jvm.linker('shared_library').flavor, 'jar')

        self.assertEqual(jvm.family, 'jvm')
        self.assertEqual(jvm.can_dual_link, False)

        self.assertEqual(jvm.compiler.deps_flavor, None)
        self.assertEqual(jvm.compiler.needs_libs, True)
        self.assertEqual(jvm.compiler.accepts_pch, False)

        self.assertRaises(AttributeError, lambda: jvm.pch_compiler)
        self.assertRaises(KeyError, lambda: jvm.linker('unknown'))
        self.assertRaises(ValueError, lambda: jvm.linker('static_library'))

    def test_oracle(self):
        def mock_execute(*args, **kwargs):
            return ('java version "1.7.0_55"\n' +
                    'Java(TM) SE Runtime Environment (build 1.7.0_55-b13)')

        version = 'javac 1.7.0_55'
        with mock.patch('bfg9000.shell.which', mock_which), \
             mock.patch('bfg9000.shell.execute', mock_execute):  # noqa
            jvm = JvmBuilder(self.env, known_langs['java'], ['javac'], version)

        self.assertEqual(jvm.brand, 'oracle')
        self.assertEqual(jvm.compiler.brand, 'oracle')
        self.assertEqual(jvm.linker('executable').brand, 'oracle')
        self.assertEqual(jvm.linker('shared_library').brand, 'oracle')

        self.assertEqual(jvm.version, Version('1.7.0'))
        self.assertEqual(jvm.compiler.version, Version('1.7.0'))
        self.assertEqual(jvm.linker('executable').version, Version('1.7.0'))
        self.assertEqual(jvm.linker('shared_library').version,
                         Version('1.7.0'))

    def test_openjdk(self):
        def mock_execute(*args, **kwargs):
            return ('openjdk version "1.8.0_151"\n' +
                    'OpenJDK Runtime Environment (build ' +
                    '1.8.0_151-8u151-b12-0ubuntu0.16.04.2-b12)')

        version = 'javac 1.8.0_151'
        with mock.patch('bfg9000.shell.which', mock_which), \
             mock.patch('bfg9000.shell.execute', mock_execute):  # noqa
            jvm = JvmBuilder(self.env, known_langs['java'], ['javac'], version)

        self.assertEqual(jvm.brand, 'openjdk')
        self.assertEqual(jvm.compiler.brand, 'openjdk')
        self.assertEqual(jvm.linker('executable').brand, 'openjdk')
        self.assertEqual(jvm.linker('shared_library').brand, 'openjdk')

        self.assertEqual(jvm.version, Version('1.8.0'))
        self.assertEqual(jvm.compiler.version, Version('1.8.0'))
        self.assertEqual(jvm.linker('executable').version, Version('1.8.0'))
        self.assertEqual(jvm.linker('shared_library').version,
                         Version('1.8.0'))

    def test_scala(self):
        version = ('Scala code runner version 2.11.6 -- ' +
                   'Copyright 2002-2013, LAMP/EPFL')
        with mock.patch('bfg9000.shell.which', mock_which):
            jvm = JvmBuilder(self.env, known_langs['scala'], ['scalac'],
                             version)

        self.assertEqual(jvm.brand, 'epfl')
        self.assertEqual(jvm.compiler.brand, 'epfl')
        self.assertEqual(jvm.linker('executable').brand, 'epfl')
        self.assertEqual(jvm.linker('shared_library').brand, 'epfl')

        self.assertEqual(jvm.version, Version('2.11.6'))
        self.assertEqual(jvm.compiler.version, Version('2.11.6'))
        self.assertEqual(jvm.linker('executable').version, Version('2.11.6'))
        self.assertEqual(jvm.linker('shared_library').version,
                         Version('2.11.6'))

    def test_unknown_brand(self):
        def mock_execute(*args, **kwargs):
            return 'unknown'

        with mock.patch('bfg9000.shell.which', mock_which), \
             mock.patch('bfg9000.shell.execute', mock_execute):  # noqa
            jvm = JvmBuilder(self.env, known_langs['java'], ['javac'],
                             'unknown')

        self.assertEqual(jvm.brand, 'unknown')
        self.assertEqual(jvm.compiler.brand, 'unknown')
        self.assertEqual(jvm.linker('executable').brand, 'unknown')
        self.assertEqual(jvm.linker('shared_library').brand, 'unknown')

        self.assertEqual(jvm.version, None)
        self.assertEqual(jvm.compiler.version, None)
        self.assertEqual(jvm.linker('executable').version, None)
        self.assertEqual(jvm.linker('shared_library').version, None)

    def test_broken_brand(self):
        def mock_execute(*args, **kwargs):
            raise OSError()

        with mock.patch('bfg9000.shell.which', mock_which), \
             mock.patch('bfg9000.shell.execute', mock_execute):  # noqa
            jvm = JvmBuilder(self.env, known_langs['java'], ['javac'],
                             'version')

        self.assertEqual(jvm.brand, 'unknown')
        self.assertEqual(jvm.compiler.brand, 'unknown')
        self.assertEqual(jvm.linker('executable').brand, 'unknown')
        self.assertEqual(jvm.linker('shared_library').brand, 'unknown')

        self.assertEqual(jvm.version, None)
        self.assertEqual(jvm.compiler.version, None)
        self.assertEqual(jvm.linker('executable').version, None)
        self.assertEqual(jvm.linker('shared_library').version, None)


class TestJvmCompiler(CrossPlatformTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(clear_variables=True, *args, **kwargs)

    def setUp(self):
        def mock_execute(*args, **kwargs):
            return 'version'

        with mock.patch('bfg9000.shell.which', mock_which), \
             mock.patch('bfg9000.shell.execute', mock_execute):  # noqa
            self.compiler = JvmBuilder(self.env, known_langs['java'],
                                       ['javac'], 'version').compiler

    def test_call(self):
        extra = self.compiler._always_flags
        with mock.patch('bfg9000.shell.which', mock_which):
            jvmout = self.env.tool('jvmoutput')
            self.assertEqual(
                self.compiler('in', 'out'),
                [jvmout, '-o', 'out', self.compiler] + extra + ['in']
            )
            self.assertEqual(
                self.compiler('in', 'out', ['flags']),
                [jvmout, '-o', 'out', self.compiler] + extra + ['flags', 'in']
            )

    def test_default_name(self):
        src = file_types.SourceFile(Path('file.java', Root.srcdir), 'java')
        self.assertEqual(self.compiler.default_name(src, None), 'file')

    def test_output_file(self):
        self.assertEqual(
            self.compiler.output_file('file', None),
            file_types.ObjectFileList(Path('file.classlist'),
                                      Path('file.class'), 'jvm', 'java')
        )

    def test_flags_empty(self):
        self.assertEqual(self.compiler.flags(opts.option_list()), [])

    def test_flags_lib(self):
        lib1 = self.Path('/path/to/lib/libfoo.jar')
        lib2 = self.Path('/path/to/lib/libbar.jar')

        self.assertEqual(self.compiler.flags(opts.option_list(
            opts.lib(file_types.StaticLibrary(lib1, 'jvm'))
        )), ['-cp', lib1])
        self.assertEqual(self.compiler.flags(opts.option_list(
            opts.lib(file_types.StaticLibrary(lib1, 'jvm')),
            opts.lib(file_types.StaticLibrary(lib2, 'jvm'))
        )), ['-cp', lib1 + os.pathsep + lib2])

    def test_flags_debug(self):
        self.assertEqual(self.compiler.flags(opts.option_list(
            opts.debug()
        )), ['-g'])

        version = ('Scala code runner version 2.11.6 -- ' +
                   'Copyright 2002-2013, LAMP/EPFL')
        with mock.patch('bfg9000.shell.which', mock_which):
            scala_compiler = JvmBuilder(self.env, known_langs['scala'],
                                        ['scalac'], version).compiler
        self.assertEqual(scala_compiler.flags(opts.option_list(
            opts.debug()
        )), ['-g:vars'])

    def test_flags_warning(self):
        self.assertEqual(self.compiler.flags(opts.option_list(
            opts.warning('disable')
        )), ['-nowarn'])
        self.assertEqual(self.compiler.flags(opts.option_list(
            opts.warning('all')
        )), ['-Xlint:all'])
        self.assertEqual(self.compiler.flags(opts.option_list(
            opts.warning('error')
        )), ['-Werror'])
        with self.assertRaises(ValueError):
            self.compiler.flags(opts.option_list(opts.warning('extra')))

        self.assertEqual(self.compiler.flags(opts.option_list(
            opts.warning('all', 'error')
        )), ['-Xlint:all', '-Werror'])

    def test_flags_warning_scala(self):
        version = ('Scala code runner version 2.11.6 -- ' +
                   'Copyright 2002-2013, LAMP/EPFL')
        with mock.patch('bfg9000.shell.which', mock_which):
            self.compiler = JvmBuilder(self.env, known_langs['scala'],
                                       ['scalac'], version).compiler

        self.assertEqual(self.compiler.flags(opts.option_list(
            opts.warning('disable')
        )), ['-nowarn'])
        self.assertEqual(self.compiler.flags(opts.option_list(
            opts.warning('all')
        )), ['-Xlint:_'])
        self.assertEqual(self.compiler.flags(opts.option_list(
            opts.warning('error')
        )), ['-Xfatal-errors'])
        with self.assertRaises(ValueError):
            self.compiler.flags(opts.option_list(opts.warning('extra')))

        self.assertEqual(self.compiler.flags(opts.option_list(
            opts.warning('all', 'error')
        )), ['-Xlint:_', '-Xfatal-errors'])

        with self.assertRaises(ValueError):
            self.compiler.flags(opts.option_list(opts.warning('unknown')))

    def test_flags_optimize(self):
        version = ('Scala code runner version 2.11.6 -- ' +
                   'Copyright 2002-2013, LAMP/EPFL')
        with mock.patch('bfg9000.shell.which', mock_which):
            self.compiler = JvmBuilder(self.env, known_langs['scala'],
                                       ['scalac'], version).compiler

        self.assertEqual(self.compiler.flags(opts.option_list(
            opts.optimize('disable')
        )), [])
        self.assertEqual(self.compiler.flags(opts.option_list(
            opts.optimize('size')
        )), ['-optimize'])
        self.assertEqual(self.compiler.flags(opts.option_list(
            opts.optimize('speed')
        )), ['-optimize'])
        self.assertEqual(self.compiler.flags(opts.option_list(
            opts.optimize('linktime')
        )), [])

        self.assertEqual(self.compiler.flags(opts.option_list(
            opts.optimize('speed', 'linktime')
        )), ['-optimize'])

    def test_flags_string(self):
        self.assertEqual(self.compiler.flags(opts.option_list('-v')), ['-v'])

    def test_flags_invalid(self):
        with self.assertRaises(TypeError):
            self.compiler.flags(opts.option_list(123))


class TestJvmLinker(CrossPlatformTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(clear_variables=True, *args, **kwargs)

    def setUp(self):
        def mock_execute(*args, **kwargs):
            return 'version'

        with mock.patch('bfg9000.shell.which', mock_which), \
             mock.patch('bfg9000.shell.execute', mock_execute):  # noqa
            self.linker = JvmBuilder(self.env, known_langs['java'], ['javac'],
                                     'version').linker('executable')

    def test_call(self):
        self.assertEqual(self.linker('in', 'out', 'manifest'),
                         [self.linker, 'out', 'manifest', 'in'])
        self.assertEqual(self.linker('in', 'out', 'manifest', ['flags']),
                         [self.linker, 'flags', 'out', 'manifest', 'in'])

    def test_output_file(self):
        self.assertEqual(self.linker.output_file('file', None),
                         file_types.Library(Path('file.jar'), 'jvm', 'java'))
        self.assertEqual(self.linker.output_file('file', AttrDict(
            options=opts.option_list(opts.entry_point('foo'))
        )), file_types.ExecutableLibrary(Path('file.jar'), 'jvm', 'java'))

    def test_flags_empty(self):
        self.assertEqual(self.linker.flags(opts.option_list()), [])

    def test_flags_string(self):
        self.assertEqual(self.linker.flags(opts.option_list('-v')), ['-v'])

    def test_flags_debug(self):
        self.assertEqual(self.linker.flags(opts.option_list(
            opts.debug()
        )), [])

    def test_flags_optimize(self):
        self.assertEqual(self.linker.flags(opts.option_list(
            opts.optimize('size')
        )), [])

    def test_flags_entry_point(self):
        self.assertEqual(self.linker.flags(opts.option_list(
            opts.entry_point('symbol')
        )), [])

    def test_flags_gui(self):
        self.assertEqual(self.linker.flags(opts.option_list(opts.gui())), [])

    def test_flags_invalid(self):
        with self.assertRaises(TypeError):
            self.linker.flags(opts.option_list(123))
