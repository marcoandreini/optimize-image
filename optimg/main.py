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
import pathlib
import os

from time import time
from xattr import getxattr, setxattr
from atomicwrites import atomic_write
from pwd import getpwnam
from grp import getgrnam


JPEGTRAN = "/opt/mozjpeg/bin/compressor"
JPEGTRAN_CMDLINE = "-copy none -opt -prog {image}"
OPTIMIZED_AT = "user.optimized_at"


class OptimizeImage:

    log = logging.getLogger("OptimizeImage")

    def __init__(self):
        parser = argparse.ArgumentParser(description='magentoimagecleanup')
        parser.add_argument('-v', '--verbose', action='store_true', default=False)
        parser.add_argument('-c', '--compressor', action='store',
                            default=JPEGTRAN,
                            help="compressor (like compressor) binary path")
        parser.add_argument('-l', '--compressor-args', action='store',
                            default=JPEGTRAN_CMDLINE, type=self.compressor_arguments,
                            help='compressor command line, must contain {image} parameter')
        parser.add_argument('-o', '--owner', action="store", type=self.to_uid,
                            help="file owner")
        parser.add_argument('-g', '--group', action="store", type=self.to_gid,
                            help="file group")
        parser.add_argument('-m', '--mode', action="store", type=self.to_mode,
                            help="file mode in octal format")
        parser.add_argument('path', metavar='IMAGESPATH',
                            help='base path of images')
        args = parser.parse_args()
        self.compressor = args.compressor
        self.compressor_args = args.compressor_args
        self.owner = args.owner
        self.group = args.group
        self.mode = args.mode
        self.path = pathlib.Path(args.path)
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
        setxattr(filename, OPTIMIZED_AT, '%3.f' % time())

    @staticmethod
    def get_optimized_at(filename):
        try:
            return float(getxattr(filename, OPTIMIZED_AT))
        except OSError:
            return None

    def run(self):

        compressor = pathlib.Path(self.compressor)
        if not compressor.exists():
            print('compressor not found in {0.compressor}'.format(self))
            return

        total_size_before = 0
        total_size_after = 0

        for img in self.path.glob("**/*.jpg"):
            stat = img.stat()
            optimized_at = self.get_optimized_at(str(img)) or 0
            if optimized_at >= stat.st_mtime:
                self.log.debug('skipping %s, image was already optimized.', str(img))
                continue
            size_before = stat.st_size
            self.log.debug("processing %s (filesize=%d)", str(img), size_before)
            total_size_before += size_before
            try:
                output = subprocess.check_output([self.compressor] +
                                                 self.compressor_args.format(image=str(img)).split())
            except subprocess.CalledProcessError:
                self.log.warn("failed compressor on %s", str(img))
                total_size_after += size_before
                continue
            size_after = len(output)
            if stat.st_size <= size_after:
                self.set_optimized_at(str(img))
                self.log.debug("skipping %s, optimization not applicable.",
                               str(img))
                # using previous size
                total_size_after += size_before
                continue
            uid = self.owner if self.owner else stat.st_uid
            gid = self.group if self.group else stat.st_gid
            mode = self.mode if self.mode else stat.st_mode
            try:
                with atomic_write(str(img), mode='wb', overwrite=True) as f:
                    f.write(output)
                    # restore permission and ownership:
                    os.chown(f.name, uid, gid)
                    os.chmod(f.name, mode)

                self.set_optimized_at(str(img))
                self.log.debug("successfully optimized %s: filesize=%d (%.2f%%)",
                               str(img), size_after,
                               (size_after - size_before) * 100.0 / size_before)
                total_size_after += size_after
            except OSError as e:
                self.log.warn("skipping %s: %s", str(img), e)
                total_size_after += size_before

        self.log.debug("total jpeg size: %d => %d (%.2f%%)",
                      total_size_before,
                      total_size_after,
                      (total_size_after - total_size_before) * 100.0 / total_size_before)


def cli():
    OptimizeImage().run()
