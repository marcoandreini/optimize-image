#!/usr/bin/python
# -*- encoding: utf-8 -*-
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import logging
import argparse
import subprocess
import os
import walkdir
import fasteners
import pyguetzli
import xattr

from time import time
from pathlib import Path
from atomicwrites import atomic_write
from pwd import getpwnam
from grp import getgrnam

# user xattr
OPTIMIZED_AT = "optimized_at"

class OptimizeImage:

    log = logging.getLogger("OptimizeImage")

    def __init__(self):
        parser = argparse.ArgumentParser(description='optimize-image')
        parser.add_argument('-v', '--verbose', action='store_true', default=False)
        parser.add_argument('-c', '--compressor', action='store',
                            default=None,
                            help="compressor binary path, default to (py)guetzli")
        parser.add_argument('-l', '--compressor-args', action='store',
                            default=None, type=self.compressor_arguments,
                            help='compressor command line, must contain {image} parameter')
        parser.add_argument('-o', '--owner', action="store", type=self.to_uid,
                            help="file owner")
        parser.add_argument('-g', '--group', action="store", type=self.to_gid,
                            help="file group")
        parser.add_argument('-m', '--mode', action="store", type=self.to_mode,
                            help="file mode in octal format")
        parser.add_argument('-x', '--exclude', action="append", default=[],
                            help='excluded directories')
        parser.add_argument('-f', '--force', action="store_true", default=False,
                            help='force optimization without check last optimization date/time')
        parser.add_argument('-t', '--max-execution-time', default=None, type=int,
                            help='max execution time in minutes')
        parser.add_argument('path', metavar='IMAGESPATH',
                            help='base path of images')
        args = parser.parse_args()
        self.compressor = args.compressor
        self.compressor_args = args.compressor_args
        self.owner = args.owner
        self.group = args.group
        self.mode = args.mode
        self.path = Path(args.path)
        self.excludes = args.exclude
        self.force = args.force
        self.max_time = None if args.max_execution_time is None \
            else time() + args.max_execution_time * 60
        logging.basicConfig(level=(logging.DEBUG if args.verbose else logging.INFO))

    @staticmethod
    def compressor_arguments(value):
        if value is None:
            return None
        try:
            value.format(image='test')
            return value
        except (KeyError, IndexError) as e:
            raise argparse.ArgumentTypeError(e)

    @staticmethod
    def to_uid(value):
        if value is None:
            return None
        try:
            return getpwnam(value).pw_uid
        except KeyError as e:
            raise argparse.ArgumentTypeError(e)

    @staticmethod
    def to_gid(value):
        if value is None:
            return None
        try:
            return getgrnam(value).gr_gid
        except KeyError as e:
            raise argparse.ArgumentTypeError(e)

    @staticmethod
    def to_mode(value):
        if value is None:
            return None
        try:
            mode = int(value, 8)
        except ValueError:
            raise argparse.ArgumentTypeError("invalid mode, must be")
        if mode < 0 or mode > 0o777:
            raise argparse.ArgumentTypeError("invalid mode")
        return mode

    @staticmethod
    def set_optimized_at(filename):
        xattr.set(filename, OPTIMIZED_AT, ('%3.f' % time()).encode(), namespace=xattr.NS_USER)

    @staticmethod
    def get_optimized_at(filename):
        try:
            return float(xattr.get(filename, OPTIMIZED_AT, namespace=xattr.NS_USER))
        except OSError:
            return None
        
    def compress(self, path):
        """
        compress jpeg "path" using internal guetzli or external subprocess
        
        """
        
        if self.compressor is None:
            with path.open('rb') as f:
                input = f.read()
                return pyguetzli.process_jpeg_bytes(input)
        else:
            return subprocess.check_output([self.compressor] +
                                           self.compressor_args.format(image=path).split())

    def run(self):
        
        lock = fasteners.InterProcessLock('/var/lock/optimize-image')
        locked = lock.acquire(blocking=False)
        if not locked:
            self.log.error('another process is in progress... exiting')
            return
        
        if self.compressor:
            self.compressor = Path(self.compressor)
            if not self.compressor.exists():
                self.log.error('compressor not found in {0.compressor}'.format(self))
                return
            self.log.debug('using {0.compressor}'.format(self))
        else:
            self.log.debug('using internal pyguetzli.')

        total_size_before = 0
        total_size_after = 0

        paths = walkdir.file_paths(walkdir.filtered_walk(str(self.path),
            included_files=['*.jpg', '*.jpeg'],
            excluded_dirs=self.excludes))
        
        for path in paths:
            if self.max_time and time() > self.max_time:
                self.log.info('maximum execution time exceeded, exiting.')
                break
            img = Path(path)
            stat = img.stat()
            optimized_at = self.get_optimized_at(path) or 0
            if not self.force and optimized_at >= stat.st_mtime:
                self.log.debug('skipping %s, image was already optimized.', path)
                continue
            size_before = stat.st_size
            self.log.debug("processing %s (filesize=%d)", path, size_before)
            total_size_before += size_before
            try:
                output = self.compress(img)
            except Exception as e:
                self.log.warn("failed optimization on %s (%s)", path, (e))
                total_size_after += size_before
                # multiple warning avoided
                self.set_optimized_at(path)
                continue
            size_after = len(output)
            if stat.st_size <= size_after:
                self.set_optimized_at(path)
                self.log.debug("skipping %s, optimization not applicable.",
                               path)
                # using previous size
                total_size_after += size_before
                continue
            uid = self.owner if self.owner else stat.st_uid
            gid = self.group if self.group else stat.st_gid
            mode = self.mode if self.mode else stat.st_mode
            try:
                with atomic_write(path, mode='wb', overwrite=True) as f:
                    f.write(output)
                    # restore permission and ownership:
                    os.chown(f.name, uid, gid)
                    os.chmod(f.name, mode)

                self.set_optimized_at(path)
                self.log.debug("successfully optimized %s: filesize=%d (%.2f%%)",
                               path, size_after,
                               (size_after - size_before) * 100.0 / size_before)
                total_size_after += size_after
            except OSError as e:
                self.log.warn("skipping %s: %s", path, e)
                total_size_after += size_before

        if total_size_before > 0:
            self.log.debug("total jpeg size: %d => %d (%.2f%%)",
                           total_size_before,
                           total_size_after,
                           (total_size_after - total_size_before) * 100.0 / total_size_before)
        else:
            self.log.debug('nothing to do.')


def cli():
    OptimizeImage().run()
