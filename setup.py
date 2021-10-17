import json
import os
import re
import subprocess
from setuptools import setup, find_packages, Command

from bfg9000.app_version import version

root_dir = os.path.abspath(os.path.dirname(__file__))


class Coverage(Command):
    description = 'run tests with code coverage'
    user_options = [
        ('test-suite=', 's',
         "test suite to run (e.g. 'some_module.test_suite')"),
    ]

    def initialize_options(self):
        self.test_suite = None

    def finalize_options(self):
        pass

    def run(self):
        env = dict(os.environ)
        pythonpath = os.path.join(root_dir, 'test', 'scripts')
        if env.get('PYTHONPATH'):
            pythonpath += os.pathsep + env['PYTHONPATH']
        env.update({
            'PYTHONPATH': pythonpath,
            'COVERAGE_FILE': os.path.join(root_dir, '.coverage'),
            'COVERAGE_PROCESS_START': os.path.join(root_dir, '.coveragerc'),
        })

        subprocess.check_call(['coverage', 'erase'])
        subprocess.check_call(
            ['coverage', 'run', 'setup.py', 'test'] +
            (['-q'] if self.verbose == 0 else []) +
            (['-s', self.test_suite] if self.test_suite else []),
            env=env
        )
        subprocess.check_call(['coverage', 'combine'])


custom_cmds = {
    'coverage': Coverage,
}

try:
    from verspec.python import Version

    class DocServe(Command):
        description = 'serve the documentation locally'
        user_options = [
            ('working', 'w', 'use the documentation in the working directory'),
            ('dev-addr=', None, 'address to host the documentation on'),
        ]

        def initialize_options(self):
            self.working = False
            self.dev_addr = '0.0.0.0:8000'

        def finalize_options(self):
            pass

        def run(self):
            cmd = 'mkdocs' if self.working else 'mike'
            subprocess.check_call([
                cmd, 'serve', '--dev-addr=' + self.dev_addr
            ])

    class DocDeploy(Command):
        description = 'push the documentation to GitHub'
        user_options = []

        def initialize_options(self):
            pass

        def finalize_options(self):
            pass

        def run(self):
            v = Version(version)
            alias = 'dev' if v.is_devrelease else 'latest'
            title = '{} ({})'.format(v.base_version, alias)
            short_version = '{}.{}'.format(*v.release[:2])

            try:
                info = json.loads(subprocess.check_output(
                    ['mike', 'list', '-j', alias],
                    universal_newlines=True
                ))
            except subprocess.CalledProcessError:
                info = None

            if info['version'] != short_version:
                t = re.sub(r' \({}\)$'.format(re.escape(alias)), '',
                           info['title'])
                subprocess.check_call(['mike', 'retitle', info['version'], t])

            subprocess.check_call(['mike', 'deploy', '-ut', title,
                                   short_version, alias])

    custom_cmds['doc_serve'] = DocServe
    custom_cmds['doc_deploy'] = DocDeploy
except ImportError:
    pass

try:
    from flake8.main.application import Application as Flake8

    class LintCommand(Command):
        description = 'run flake8 on source code'
        user_options = []

        def initialize_options(self):
            pass

        def finalize_options(self):
            pass

        def distribution_files(self):
            return ['mkdocs.py', 'setup.py', 'bfg9000', 'examples', 'test']

        def run(self):
            flake8 = Flake8()
            flake8.initialize([])
            flake8.run_checks(list(self.distribution_files()))
            flake8.formatter.start()
            flake8.report_errors()
            flake8.report_statistics()
            flake8.report_benchmarks()
            flake8.formatter.stop()
            try:
                flake8.exit()
            except SystemExit as e:
                # If successful, don't exit. This allows other commands to run
                # too.
                if e.code:
                    raise

    custom_cmds['lint'] = LintCommand
except ImportError:
    pass

more_requires = []

if os.getenv('STDEB_BUILD') not in ['1', 'true']:
    more_requires.extend([
        'doppel >= 0.4.0',
        'mopack',
        'pysetenv;platform_system=="Windows"'
    ])
    if os.getenv('NO_PATCHELF') not in ['1', 'true']:
        more_requires.append('patchelf-wrapper;platform_system=="Linux"')

with open(os.path.join(root_dir, 'README.md'), 'r') as f:
    # Read from the file and strip out the badges.
    long_desc = re.sub(r'(^# bfg9000.*)\n\n(.+\n)*', r'\1', f.read())

setup(
    name='bfg9000',
    version=version,

    description='A cross-platform build file generator',
    long_description=long_desc,
    long_description_content_type='text/markdown',
    keywords='build file generator',
    url='https://jimporter.github.io/bfg9000/',

    author='Jim Porter',
    author_email='itsjimporter@gmail.com',
    license='BSD',

    classifiers=[
        'Development Status :: 3 - Alpha',

        'Intended Audience :: Developers',

        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: BSD License',

        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],

    packages=find_packages(exclude=['test', 'test.*']),

    python_requires='>=3.6',
    install_requires=(
        ['colorama', 'pyyaml', 'setuptools', 'verspec'] + more_requires
    ),
    extras_require={
        'dev': ['coverage', 'flake8 >= 3.7', 'lxml', 'mike >= 0.3.1',
                'mkdocs-bootswatch', 'mkdocs-macros-plugin', 'shtab', 'stdeb'],
        'test': ['coverage', 'flake8 >= 3.7', 'lxml', 'shtab'],
        'msbuild': ['lxml'],
    },

    entry_points={
        'console_scripts': [
            'bfg9000=bfg9000.driver:main',
            '9k=bfg9000.driver:simple_main',
            'bfg9000-depfixer=bfg9000.depfixer:main',
            'bfg9000-jvmoutput=bfg9000.jvmoutput:main',
            'bfg9000-rccdep=bfg9000.rccdep:main',
        ],
        'bfg9000.backends': [
            'make=bfg9000.backends.make.writer',
            'ninja=bfg9000.backends.ninja.writer',
            'msbuild=bfg9000.backends.msbuild.writer [msbuild]',
        ],
        'bfg9000.platforms.host': [
            'cygwin=bfg9000.platforms.cygwin:CygwinHostPlatform',
            'darwin=bfg9000.platforms.posix:DarwinHostPlatform',
            'linux=bfg9000.platforms.posix:PosixHostPlatform',
            'msdos=bfg9000.platforms.windows:WindowsTargetPlatform',
            'posix=bfg9000.platforms.posix:PosixHostPlatform',
            'win9x=bfg9000.platforms.windows:WindowsHostPlatform',
            'winnt=bfg9000.platforms.windows:WindowsHostPlatform',
        ],
        'bfg9000.platforms.target': [
            'cygwin=bfg9000.platforms.cygwin:CygwinTargetPlatform',
            'darwin=bfg9000.platforms.posix:DarwinTargetPlatform',
            'linux=bfg9000.platforms.posix:PosixTargetPlatform',
            'msdos=bfg9000.platforms.windows:WindowsTargetPlatform',
            'posix=bfg9000.platforms.posix:PosixTargetPlatform',
            'win9x=bfg9000.platforms.windows:WindowsTargetPlatform',
            'winnt=bfg9000.platforms.windows:WindowsTargetPlatform',
        ],
    },

    test_suite='test',
    cmdclass=custom_cmds,
)
