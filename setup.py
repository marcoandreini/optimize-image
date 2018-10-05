#!/usr/bin/env python

from setuptools import setup, find_packages

__author__ = 'Marco Andreini'
__version__ = '0.2.0'
__contact__ = 'marco.andreini@gmail.com'
__url__ = 'https://github.com/marcoandreini/optimize-image'
__license__ = 'GPLv3'


setup(name='optimize-image',
      version=__version__,
      description='Optimize image via guetzli',
      author=__author__,
      author_email=__contact__,
      url=__url__,
      license=__license__,
      packages=find_packages(),
      entry_points='''
        [console_scripts]
        optimize-image=optimg.main:cli
      ''',
      install_requires=['atomicwrites>=1.2.1', 'pathlib', 'pyxattr>=0.6.0',
                        'walkdir>=0.4.1', 'fasteners', 'pyguetzli'],
      classifiers=[
        'Intended Audience :: Developers',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Environment :: Console',
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)'
      ]
     )
