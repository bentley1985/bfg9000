import os
from contextlib import contextmanager, ExitStack
from unittest import mock

from .. import TestCase
from .common import BuiltinTest

from bfg9000.builtins import find, project, regenerate, version  # noqa: F401
from bfg9000.file_types import Directory, File, HeaderDirectory, SourceFile
from bfg9000.iterutils import uniques
from bfg9000.path import Path, Root
from bfg9000.platforms import known_platforms

path_vars = {
    Root.srcdir: None,
    Root.builddir: None,
}


def srcpath(p):
    return Path(p, Root.srcdir)


@contextmanager
def mock_filesystem():
    def mock_listdir(path):
        basename = os.path.basename(path)
        if basename == 'dir':
            return ['file2.txt', 'sub']
        elif basename in ['dir2', 'sub']:
            return []
        return ['file.cpp', 'file.cpp~', 'dir', 'dir2']

    def mock_exists(path, variables=None):
        if path.suffix == '':
            return True
        paths = mock_listdir(path.parent().suffix)
        return path.basename() in paths

    def mock_isdir(path, variables=None):
        return not path.basename().startswith('file')

    with mock.patch('os.listdir', mock_listdir) as a, \
         mock.patch('bfg9000.path.exists', mock_exists) as b, \
         mock.patch('bfg9000.path.isdir', mock_isdir) as c, \
         mock.patch('bfg9000.path.islink', return_value=False) as d:
        yield a, b, c, d


class TestFindResult(TestCase):
    def test_bool(self):
        R = find.FindResult
        self.assertTrue(bool(R.include))
        self.assertFalse(bool(R.not_now))
        self.assertFalse(bool(R.exclude))
        self.assertFalse(bool(R.exclude_recursive))

    def test_and(self):
        R = find.FindResult
        self.assertEqual(R.include & R.include, R.include)
        self.assertEqual(R.include & R.not_now, R.not_now)
        self.assertEqual(R.include & R.exclude, R.exclude)
        self.assertEqual(R.include & R.exclude_recursive, R.exclude_recursive)

        self.assertEqual(R.not_now & R.include, R.not_now)
        self.assertEqual(R.not_now & R.not_now, R.not_now)
        self.assertEqual(R.not_now & R.exclude, R.exclude)
        self.assertEqual(R.not_now & R.exclude_recursive, R.exclude_recursive)

        self.assertEqual(R.exclude & R.include, R.exclude)
        self.assertEqual(R.exclude & R.not_now, R.exclude)
        self.assertEqual(R.exclude & R.exclude, R.exclude)
        self.assertEqual(R.exclude & R.exclude_recursive, R.exclude_recursive)

        self.assertEqual(R.exclude_recursive & R.include, R.exclude_recursive)
        self.assertEqual(R.exclude_recursive & R.not_now, R.exclude_recursive)
        self.assertEqual(R.exclude_recursive & R.exclude, R.exclude_recursive)
        self.assertEqual(R.exclude_recursive & R.exclude_recursive,
                         R.exclude_recursive)

    def test_or(self):
        R = find.FindResult
        self.assertEqual(R.include | R.include, R.include)
        self.assertEqual(R.include | R.not_now, R.include)
        self.assertEqual(R.include | R.exclude, R.include)
        self.assertEqual(R.include | R.exclude_recursive, R.include)

        self.assertEqual(R.not_now | R.include, R.include)
        self.assertEqual(R.not_now | R.not_now, R.not_now)
        self.assertEqual(R.not_now | R.exclude, R.not_now)
        self.assertEqual(R.not_now | R.exclude_recursive, R.not_now)

        self.assertEqual(R.exclude | R.include, R.include)
        self.assertEqual(R.exclude | R.not_now, R.not_now)
        self.assertEqual(R.exclude | R.exclude, R.exclude)
        self.assertEqual(R.exclude | R.exclude_recursive, R.exclude)

        self.assertEqual(R.exclude_recursive | R.include, R.include)
        self.assertEqual(R.exclude_recursive | R.not_now, R.not_now)
        self.assertEqual(R.exclude_recursive | R.exclude, R.exclude)
        self.assertEqual(R.exclude_recursive | R.exclude_recursive,
                         R.exclude_recursive)


class TestFileFilter(TestCase):
    def test_file(self):
        f = find.FileFilter('*')
        self.assertEqual(f.match(srcpath('foo')), find.FindResult.include)
        self.assertEqual(f.match(srcpath('foo/')), find.FindResult.exclude)

    def test_dir(self):
        f = find.FileFilter('*/')
        self.assertEqual(f.match(srcpath('foo')), find.FindResult.exclude)
        self.assertEqual(f.match(srcpath('foo/')), find.FindResult.include)

    def test_either(self):
        f = find.FileFilter('*', '*')
        self.assertEqual(f.match(srcpath('foo')), find.FindResult.include)
        self.assertEqual(f.match(srcpath('foo/')), find.FindResult.include)

    def test_include(self):
        f = find.FileFilter('*.hpp')
        self.assertEqual(f.match(srcpath('foo.hpp')), find.FindResult.include)
        self.assertEqual(f.match(srcpath('foo.cpp')),
                         find.FindResult.exclude_recursive)

    def test_multiple_include(self):
        f = find.FileFilter(['*.hpp', '*.cpp'])
        self.assertEqual(f.match(srcpath('foo.hpp')), find.FindResult.include)
        self.assertEqual(f.match(srcpath('foo.cpp')), find.FindResult.include)
        self.assertEqual(f.match(srcpath('foo.txt')),
                         find.FindResult.exclude_recursive)

    def test_extra(self):
        f = find.FileFilter('*.cpp', extra='*.hpp')
        self.assertEqual(f.match(srcpath('foo.hpp')), find.FindResult.not_now)
        self.assertEqual(f.match(srcpath('foo.cpp')), find.FindResult.include)
        self.assertEqual(f.match(srcpath('foo.txt')),
                         find.FindResult.exclude_recursive)

    def test_pattern_extra_overlap(self):
        f = find.FileFilter('*.hpp', extra='*.?pp')
        self.assertEqual(f.match(srcpath('foo.hpp')), find.FindResult.include)
        self.assertEqual(f.match(srcpath('foo.cpp')), find.FindResult.not_now)
        self.assertEqual(f.match(srcpath('foo.cxx')),
                         find.FindResult.exclude_recursive)

    def test_multiple_extra(self):
        f = find.FileFilter('*.cpp', extra=['*.hpp', '*.ipp'])
        self.assertEqual(f.match(srcpath('foo.hpp')), find.FindResult.not_now)
        self.assertEqual(f.match(srcpath('foo.ipp')), find.FindResult.not_now)
        self.assertEqual(f.match(srcpath('foo.cpp')), find.FindResult.include)
        self.assertEqual(f.match(srcpath('foo.txt')),
                         find.FindResult.exclude_recursive)

    def test_exclude(self):
        f = find.FileFilter('*.?pp', exclude='*.cpp')
        self.assertEqual(f.match(srcpath('foo.hpp')), find.FindResult.include)
        self.assertEqual(f.match(srcpath('foo.cpp')),
                         find.FindResult.exclude_recursive)

    def test_recursive_exclude(self):
        f = find.FileFilter('*.cpp', exclude=['dir/'])
        self.assertEqual(f.match(srcpath('foo.cpp')), find.FindResult.include)
        self.assertEqual(f.match(srcpath('dir/')),
                         find.FindResult.exclude_recursive)
        self.assertEqual(f.match(srcpath('dir/foo.cpp')),
                         find.FindResult.exclude_recursive)

    def test_multiple_exclude(self):
        f = find.FileFilter('*.?pp', exclude=['*.cpp', '*.hpp'])
        self.assertEqual(f.match(srcpath('foo.ipp')), find.FindResult.include)
        self.assertEqual(f.match(srcpath('foo.hpp')),
                         find.FindResult.exclude_recursive)
        self.assertEqual(f.match(srcpath('foo.cpp')),
                         find.FindResult.exclude_recursive)

    def test_extra_exclude(self):
        f = find.FileFilter('*.c??', extra='*.?pp', exclude='*.hpp')
        self.assertEqual(f.match(srcpath('foo.cpp')), find.FindResult.include)
        self.assertEqual(f.match(srcpath('foo.ipp')), find.FindResult.not_now)
        self.assertEqual(f.match(srcpath('foo.hpp')),
                         find.FindResult.exclude_recursive)

    def test_no_pattern(self):
        self.assertRaises(ValueError, find.FileFilter, [])
        self.assertRaises(ValueError, find.FileFilter, None)


class TestFilterByPlatform(BuiltinTest):
    def setUp(self):
        super().setUp()
        self.filter = self.context['filter_by_platform']

    def test_normal(self):
        self.assertEqual(self.filter(Path('file.txt')),
                         find.FindResult.include)

    def do_test_platform(self, platform, result):
        paths = [Path('{}/file.txt'.format(platform)),
                 Path('dir/{}/file.txt'.format(platform)),
                 Path('file_{}.txt'.format(platform)),
                 Path('dir_{}/file.txt'.format(platform))]
        for p in paths:
            self.assertEqual(self.filter(p), result, repr(p))

    def test_current_platform(self):
        self.do_test_platform(self.env.target_platform.genus,
                              find.FindResult.include)
        self.do_test_platform(self.env.target_platform.family,
                              find.FindResult.include)

    def test_non_current_platform(self):
        my_plat = {self.env.target_platform.genus,
                   self.env.target_platform.family}
        for i in known_platforms:
            if i not in my_plat:
                self.do_test_platform(i, find.FindResult.not_now)


class FindTestCase(BuiltinTest):
    def setUp(self):
        super().setUp()
        with ExitStack() as stack:
            self._ctx = stack.enter_context(mock_filesystem())
            self.addCleanup(stack.pop_all().close)


class TestFind(FindTestCase):
    def test_default(self):
        self.assertPathListEqual(
            find.find(self.env, '**'),
            [srcpath('file.cpp'), srcpath('file.cpp~'),
             srcpath('dir/file2.txt')]
        )
        self.assertPathListEqual(
            find.find(self.env, '**/'),
            [srcpath('./'), srcpath('dir/'), srcpath('dir2/'),
             srcpath('dir/sub/')]
        )

    def test_file(self):
        self.assertPathListEqual(
            find.find(self.env, '**', type='f'),
            [srcpath('file.cpp'), srcpath('file.cpp~'),
             srcpath('dir/file2.txt')]
        )

    def test_dir(self):
        self.assertPathListEqual(
            find.find(self.env, '**', type='d'),
            [srcpath('./'), srcpath('dir/'), srcpath('dir2/'),
             srcpath('dir/sub/')]
        )

    def test_any(self):
        self.assertPathListEqual(
            find.find(self.env, '**', type='*'),
            [srcpath('./'), srcpath('dir/'),  srcpath('dir2/'),
             srcpath('file.cpp'), srcpath('file.cpp~'), srcpath('dir/sub/'),
             srcpath('dir/file2.txt')]
        )

    def test_multiple_patterns(self):
        self.assertPathListEqual(
            find.find(self.env, ['*.cpp', 'dir/*.txt']),
            [srcpath('file.cpp'), srcpath('dir/file2.txt')]
        )


class TestFindFiles(FindTestCase):
    def setUp(self):
        super().setUp()
        self.find = self.context['find_files']
        self.dist = []

    def assertFoundResult(self, result, expected):
        self.assertEqual(result, expected)

    def assertFound(self, result, expected, *, pre=[], post=[]):
        self.assertFoundResult(result, expected)
        self.dist = uniques(self.dist + pre + expected + post)
        self.assertEqual(list(self.build.sources()),
                         [self.bfgfile] + self.dist)

    def assertFindDirs(self, expected):
        self.assertPathSetEqual(self.build['find_dirs'], expected)

    def test_str_pattern(self):
        expected = [File(srcpath('dir/file2.txt'))]
        self.assertFound(self.find('dir/**'), expected)
        self.assertFindDirs({srcpath('dir/'), srcpath('dir/sub/')})

        expected = [Directory(srcpath('dir/')),
                    Directory(srcpath('dir/sub'))]
        self.assertFound(self.find('dir/**/'), expected)
        self.assertFindDirs({srcpath('dir/'), srcpath('dir/sub/')})

    def test_path_pattern(self):
        expected = [File(srcpath('dir/file2.txt'))]
        self.assertFound(self.find(srcpath('dir/**')), expected)
        self.assertFindDirs({srcpath('dir/'), srcpath('dir/sub/')})

        expected = [Directory(srcpath('dir/')),
                    Directory(srcpath('dir/sub'))]
        self.assertFound(self.find(srcpath('dir/**/')), expected)
        self.assertFindDirs({srcpath('dir/'), srcpath('dir/sub/')})

    def test_multiple_patterns(self):
        expected = [SourceFile(srcpath('file.cpp'), 'c++'),
                    File(srcpath('dir/file2.txt'))]
        self.assertFound(self.find(['*.cpp', 'dir/*.txt']), expected)
        self.assertFindDirs({srcpath('./'), srcpath('dir/')})

    def test_submodule(self):
        with self.context.push_path(Path('dir/build.bfg', Root.srcdir)):
            expected = [File(srcpath('dir/file2.txt'))]
            self.assertFound(self.find('**'), expected)
            self.assertFindDirs({srcpath('dir/'), srcpath('dir/sub/')})

            expected = [Directory(srcpath('dir/')),
                        Directory(srcpath('dir/sub'))]
            self.assertFound(self.find('**/'), expected)
            self.assertFindDirs({srcpath('dir/'), srcpath('dir/sub/')})

    def test_submodule_parent(self):
        with self.context.push_path(Path('dir/build.bfg', Root.srcdir)):
            expected = [SourceFile(srcpath('file.cpp'), 'c++'),
                        File(srcpath('dir/file2.txt'))]
            self.assertFound(self.find('../**'), expected)
            self.assertFindDirs({srcpath('./'), srcpath('dir/'),
                                 srcpath('dir2/'), srcpath('dir/sub/')})

            expected = [Directory(srcpath('./')),
                        Directory(srcpath('dir/')),
                        Directory(srcpath('dir2')),
                        Directory(srcpath('dir/sub'))]
            self.assertFound(self.find('../**/'), expected)
            self.assertFindDirs({srcpath('./'), srcpath('dir/'),
                                 srcpath('dir2/'), srcpath('dir/sub/')})

    def test_submodule_path_object(self):
        with self.context.push_path(Path('dir/build.bfg', Root.srcdir)):
            expected = [SourceFile(srcpath('file.cpp'), 'c++'),
                        File(srcpath('dir/file2.txt'))]
            self.assertFound(self.find(srcpath('**')), expected)
            self.assertFindDirs({srcpath('./'), srcpath('dir/'),
                                 srcpath('dir2/'), srcpath('dir/sub/')})

            expected = [Directory(srcpath('.')),
                        Directory(srcpath('dir')),
                        Directory(srcpath('dir2')),
                        Directory(srcpath('dir/sub'))]
            self.assertFound(self.find(srcpath('**/')), expected)
            self.assertFindDirs({srcpath('./'), srcpath('dir/'),
                                 srcpath('dir2/'), srcpath('dir/sub/')})

    def test_type_file(self):
        expected = [SourceFile(srcpath('file.cpp'), 'c++'),
                    File(srcpath('dir/file2.txt'))]
        self.assertFound(self.find('**', type='f'), expected)
        self.assertFindDirs({srcpath('./'), srcpath('dir/'), srcpath('dir2/'),
                             srcpath('dir/sub/')})

    def test_type_dir(self):
        expected = [Directory(srcpath('.')),
                    Directory(srcpath('dir')),
                    Directory(srcpath('dir2')),
                    Directory(srcpath('dir/sub'))]
        self.assertFound(self.find('**', type='d'), expected)
        self.assertFindDirs({srcpath('./'), srcpath('dir/'), srcpath('dir2/'),
                             srcpath('dir/sub/')})

    def test_type_all(self):
        expected = [Directory(srcpath('.')),
                    Directory(srcpath('dir')),
                    Directory(srcpath('dir2')),
                    SourceFile(srcpath('file.cpp'), 'c++'),
                    Directory(srcpath('dir/sub')),
                    File(srcpath('dir/file2.txt'))]
        self.assertFound(self.find('**', type='*'), expected)
        self.assertFindDirs({srcpath('./'), srcpath('dir/'), srcpath('dir2/'),
                             srcpath('dir/sub/')})

    def test_extra(self):
        expected = [SourceFile(srcpath('file.cpp'), 'c++')]
        extra = [File(srcpath('dir/file2.txt'))]
        self.assertFound(self.find('**/*.cpp', extra='*.txt'), expected,
                         post=extra)
        self.assertFindDirs({srcpath('./'), srcpath('dir/'), srcpath('dir2/'),
                             srcpath('dir/sub/')})

    def test_multiple_extra(self):
        expected = [SourceFile(srcpath('file.cpp'), 'c++')]
        extra = [Directory(srcpath('dir/sub')),
                 File(srcpath('dir/file2.txt'))]
        self.assertFound(self.find('**/*.cpp', extra=['*.txt', 'su?/']),
                         expected, post=extra)
        self.assertFindDirs({srcpath('./'), srcpath('dir/'), srcpath('dir2/'),
                             srcpath('dir/sub/')})

    def test_exclude(self):
        expected = [SourceFile(srcpath('file.cpp'), 'c++')]
        self.assertFound(self.find('**/file*', exclude='dir/'), expected)
        self.assertFindDirs({srcpath('./'), srcpath('dir2/')})

    def test_multiple_exclude(self):
        expected = [SourceFile(srcpath('file.cpp'), 'c++')]
        self.assertFound(self.find('**/file*', exclude=['*.txt', 'sub/']),
                         expected)
        self.assertFindDirs({srcpath('./'), srcpath('dir/'), srcpath('dir2/')})

    def test_exclude_all_files(self):
        self.assertFound(self.find('**', exclude=['*']), [])
        self.assertFindDirs({srcpath('./'), srcpath('dir/'), srcpath('dir2/'),
                             srcpath('dir/sub/')})

    def test_no_default_exclude(self):
        self.context['project'](find_exclude=[])
        expected = [SourceFile(srcpath('file.cpp'), 'c++'),
                    File(srcpath('file.cpp~')),
                    File(srcpath('dir/file2.txt'))]
        self.assertFound(self.find('**/file*'), expected)
        self.assertFindDirs({srcpath('./'), srcpath('dir/'), srcpath('dir2/'),
                             srcpath('dir/sub/')})

    def test_custom_default_exclude(self):
        self.context['project'](find_exclude=['*.txt'])
        expected = [SourceFile(srcpath('file.cpp'), 'c++'),
                    File(srcpath('file.cpp~'))]
        self.assertFound(self.find('**/file*'), expected)
        self.assertFindDirs({srcpath('./'), srcpath('dir/'), srcpath('dir2/'),
                             srcpath('dir/sub/')})

    def test_filter(self):
        def my_filter(path):
            if path.directory:
                return find.FindResult.not_now
            elif path.ext() == '.cpp':
                return find.FindResult.include
            else:
                return find.FindResult.exclude

        expected = [SourceFile(srcpath('file.cpp'), 'c++')]
        pre = [Directory(srcpath('./')),
               Directory(srcpath('dir/')),
               Directory(srcpath('dir2/'))]
        post = [Directory(srcpath('dir/sub/'))]
        self.assertFound(self.find('**', type='*', filter=my_filter), expected,
                         pre=pre, post=post)
        self.assertFindDirs({srcpath('./'), srcpath('dir/'), srcpath('dir2/'),
                             srcpath('dir/sub/')})

    def test_glob_with_filters(self):
        def my_filter(path):
            return (find.FindResult.exclude_recursive if path.directory else
                    find.FindResult.include)

        expected = [SourceFile(srcpath('file.cpp'), 'c++')]
        self.assertFound(self.find('**/file*', filter=my_filter), expected)
        self.assertFindDirs({srcpath('./')})

    def test_file_types(self):
        f = self.context['generic_file']
        d = self.context['header_directory']
        expected = [File(srcpath('file.cpp')),
                    File(srcpath('dir/file2.txt'))]
        self.assertFound(self.find('**', file_type=f), expected)
        self.assertFindDirs({srcpath('./'), srcpath('dir/'), srcpath('dir2/'),
                             srcpath('dir/sub/')})

        expected = [HeaderDirectory(srcpath('.')),
                    HeaderDirectory(srcpath('dir')),
                    HeaderDirectory(srcpath('dir2')),
                    HeaderDirectory(srcpath('dir/sub'))]
        self.assertFound(self.find('**/', dir_type=d), expected)
        self.assertFindDirs({srcpath('./'), srcpath('dir/'), srcpath('dir2/'),
                             srcpath('dir/sub/')})

        expected = [HeaderDirectory(srcpath('.')),
                    HeaderDirectory(srcpath('dir')),
                    HeaderDirectory(srcpath('dir2')),
                    File(srcpath('file.cpp')),
                    HeaderDirectory(srcpath('dir/sub')),
                    File(srcpath('dir/file2.txt'))]
        self.assertFound(self.find('**', type='*', file_type=f,
                                   dir_type=d), expected)
        self.assertFindDirs({srcpath('./'), srcpath('dir/'), srcpath('dir2/'),
                             srcpath('dir/sub/')})

    def test_no_dist(self):
        expected = [SourceFile(srcpath('file.cpp'), 'c++'),
                    File(srcpath('dir/file2.txt'))]
        self.assertFoundResult(self.find('**', dist=False), expected)
        self.assertEqual(list(self.build.sources()), [self.bfgfile])
        self.assertFindDirs({srcpath('./'), srcpath('dir/'), srcpath('dir2/'),
                             srcpath('dir/sub/')})

    def test_no_cache(self):
        expected = [SourceFile(srcpath('file.cpp'), 'c++'),
                    File(srcpath('dir/file2.txt'))]
        self.assertFound(self.find('**', cache=False), expected)
        self.assertFindDirs(set())


class TestFindPaths(TestFindFiles):
    def setUp(self):
        super().setUp()
        self.find = self.context['find_paths']

    def assertFoundResult(self, result, expected):
        self.assertPathListEqual(result, [i.path for i in expected])
