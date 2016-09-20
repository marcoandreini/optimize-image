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

from atomicwrites import atomic_write
from pwd import getpwnam
from grp import getgrnam


JPEGTRAN = "/opt/mozjpeg/bin/jpegtran"
JPEGTRAN_CMDLINE = ["-copy", "none", "-opt", "-prog"]


class OptimizeImage:

    log = logging.getLogger("OptimizeImage")

    def __init__(self):
        parser = argparse.ArgumentParser(description='magentoimagecleanup')
        parser.add_argument('-v', '--verbose', action='store_true', default=False)
        parser.add_argument('-j', '--jpegtran', action="store",
                            default=JPEGTRAN, help="jpegtran binary path")
        parser.add_argument('-o', '--owner', action="store", type=self.to_uid,
                            help="file owner")
        parser.add_argument('-g', '--group', action="store", type=self.to_gid,
                            help="file group")
        parser.add_argument('-m', '--mode', action="store", type=self.to_mode,
                            help="file mode in octal format")
        parser.add_argument('path', metavar='IMAGESPATH',
                            help='base path of images')
        args = parser.parse_args()
        self.jpegtran = args.jpegtran
        self.owner = args.owner
        self.group = args.group
        self.mode = args.mode
        self.path = pathlib.Path(args.path)
        logging.basicConfig(level=(logging.DEBUG if args.verbose else logging.INFO))

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

    def run(self):

        jpegtran = pathlib.Path(self.jpegtran)
        if not jpegtran.exists():
            print('jpegtran not found in {0.jpegtran}'.format(self))
            return

        total_size_before = 0
        total_size_after = 0

        for img in self.path.glob("**/*.jpg"):
            stat = img.stat()
            size_before = stat.st_size
            self.log.debug("processing %s (filesize=%d)", str(img), size_before)
            total_size_before += size_before
            try:
                output = subprocess.check_output([self.jpegtran] + JPEGTRAN_CMDLINE + [str(img)])
            except subprocess.CalledProcessError as e:
                self.log.warn("failed jpegtran on %s. %s",
                               str(img), e.output.decode('utf-8'))
                total_size_after += size_before
                continue
            size_after = len(output)
            if stat.st_size <= size_after:
                self.log.debug("skipping %s, optimization not applicable.",
                               str(img))
                # using previous size
                total_size_after += size_before
                continue
            uid = self.owner if self.owner else stat.st_uid
            gid = self.group if self.group else stat.st_gid
            mode = self.mode if self.mode else stat.st_mode
            with atomic_write(str(img), mode='wb', overwrite=True) as f:
                f.write(output)
                # restore permission and ownership:
                os.chown(f.name, uid, gid)
                os.chmod(f.name, mode)
            self.log.debug("successfully optimized %s: filesize=%d (%.2f%%)",
                           str(img), size_after,
                           (size_after - size_before) * 100.0 / size_before)
            total_size_after += size_after

        self.log.debug("total jpeg size: %d => %d (%.2f%%)",
                      total_size_before,
                      total_size_after,
                      (total_size_after - total_size_before) * 100.0 / total_size_before)


def cli():
    OptimizeImage().run()
