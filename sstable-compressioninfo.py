#!/usr/bin/env python3

"""
Copyright (C) 2019 ScyllaDB
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
    http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import argparse
import binascii
import struct
import sstable_tools.sstablelib as sstablelib
import itertools
import operator
import statistics
import textwrap

cmdline_parser = argparse.ArgumentParser()
cmdline_parser.add_argument(
    "compressioninfo_file", nargs="+", help="CompressionInfo file(s) to parse"
)
cmdline_parser.add_argument(
    "--summary", action="store_true", help="generate a summary instead of full output"
)

args = cmdline_parser.parse_args()

for fname in args.compressioninfo_file:
    s = sstablelib.Stream(open(fname, "rb").read())
    algo = s.string16()
    options = s.map32()
    chunk_size = s.int32()
    data_len = s.int64()
    offsets = s.array32(sstablelib.Stream.int64)
    end = offsets[1:] + [offsets[-1]]
    diffs = list(itertools.starmap(operator.__sub__, zip(end, offsets)))
    avg_chunk = int(statistics.mean(diffs[:-1]))
    min_chunk = min(diffs[:-1])
    max_chunk = max(diffs[:-1])
    nr_chunks = len(offsets)

    if args.summary:
        print(
            "{data_len:12} {chunk_size:6} {min_chunk:6} {avg_chunk:6} {max_chunk:6} {fname}".format(
                **locals()
            )
        )
    else:
        print(
            textwrap.dedent(
                """
            File: {fname}
            Algorithm: {algo}
            Options: {options}
            Chunk size: {chunk_size}
            Data length: {data_len}
            Number of chunks: {nr_chunks}
            Offsets:"""
            ).format(**locals())
        )
        for offset in offsets:
            print("    {offset}".format(**locals()))
        print()
