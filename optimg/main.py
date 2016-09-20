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

JPEGTRAN = "/opt/mozjpeg/bin/jpegtran"
JPEGTRAN_CMDLINE = ["-copy", "none", "-opt", "-prog"]

class OptimizeImage:

    log = logging.getLogger("OptimizeImage")

    def __init__(self):
        parser = argparse.ArgumentParser(description='magentoimagecleanup')
        parser.add_argument('-v', '--verbose', action='store_true', default=False)
        parser.add_argument('path', metavar='IMAGESPATH',
                            help='base path of images')
        parser.add_argument('-j', '--jpegtran', action="store",
                            default=JPEGTRAN, help="jpegtran binary path")
        args = parser.parse_args()
        self.jpegtran = args.jpegtran
        self.path = pathlib.Path(args.path)
        logging.basicConfig(level=(logging.DEBUG if args.verbose else logging.INFO))

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
            if stat.st_size <= size_after and False:
                self.log.debug("skipping %s, optimization not applicable.",
                               str(img))
                # using previous size
                total_size_after += size_before
                continue
            with atomic_write(str(img), mode='wb', overwrite=True) as f:
                f.write(output)
                # restore permission and ownership:
                os.chown(f.name, stat.st_uid, stat.st_gid)
                os.chmod(f.name, stat.st_mode)
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
