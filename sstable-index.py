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

cmdline_parser = argparse.ArgumentParser()
cmdline_parser.add_argument("index_file", nargs="+", help="index file to parse")
cmdline_parser.add_argument(
    "--summary", action="store_true", help="generate a summary instead of full output"
)
cmdline_parser.add_argument(
    "--partition-size-threshold",
    type=int,
    default=-2,
    help="report on partitions this size or larger",
)
cmdline_parser.add_argument(
    "--ignore-missing",
    action="store_true",
    default=False,
    help="ignore missing files (useful when running on live data that can be compacted)",
)

args = cmdline_parser.parse_args()


class FullReport:
    def report_file(self, file):
        print("Parsing {}".format(file))

    def begin_entries(self):
        print("Index entries:")

    def report_partition_start(self, key, position, promoted_length, partition_size):
        print(
            "\tKey:\t\t\t{}\n\tPosition:\t\t{}\n\tPromoted length:\t{}".format(
                binascii.hexlify(key), position, promoted_length
            )
        )
        print("\tPartition size:\t{}".format(partition_size))

    def report_promoted_start(self, deletion_time, timestamp, entries_count):
        print(
            "\tDeletion time:\t\t{}\n\tTimestamp:\t\t{}\n\tEntries count:\t\t{}".format(
                deletion_time, timestamp, entries_count
            )
        )

    def report_promoted_entry(self, start, end, entry_offset, width):
        print(
            "\t\tStart:\t{}\n\t\tEnd:\t{}\n\t\tOffset:\t{}\n\t\tLength:\t{}\n".format(
                binascii.hexlify(start), binascii.hexlify(end), entry_offset, width
            )
        )

    def report_partition_end(self):
        print("")

    def report_end(self, partitions):
        print("Total partitions:\t\t\t{}".format(partitions))


class SummaryReport:
    def report_file(self, file):
        self.file = file

    def begin_entries(self):
        pass

    def report_partition_start(self, key, position, promoted_length, partition_size):
        self.key = key
        self.position = position
        self.promoted_length = promoted_length
        self.partition_size = partition_size

    def report_promoted_start(self, deletion_time, timestamp, entries_count):
        pass

    def report_promoted_entry(self, start, end, entry_offset, width):
        pass

    def report_partition_end(self):
        print(
            "{:12} {:9} {:12} {} {}".format(
                self.position,
                self.promoted_length,
                self.partition_size,
                binascii.hexlify(self.key),
                self.file,
            )
        )

    def report_end(self, partitions):
        pass


class NullReport:
    def report_file(self, file):
        pass

    def begin_entries(self):
        pass

    def report_partition_start(self, key, position, promoted_length, partition_size):
        pass

    def report_promoted_start(self, deletion_time, timestamp, entries_count):
        pass

    def report_promoted_entry(self, start, end, entry_offset, width):
        pass

    def report_partition_end(self):
        pass

    def report_end(self, partitions):
        pass


reporter = FullReport()
if args.summary:
    reporter = SummaryReport()

for index_file in args.index_file:
    reporter.report_file(index_file)

    try:
        file = open(index_file, "rb")
    except:
        if args.ignore_missing:
            print("File {} missing, possible compacted".format(index_file))
            continue
        else:
            raise

    data = file.read()

    offset = 0
    size = len(data)

    reporter.begin_entries()
    partitions = 0

    while offset < size:
        partitions += 1

        key_length = struct.unpack_from(">h", data, offset)[0]
        key = struct.unpack_from(">{}s".format(key_length), data, offset + 2)[0]
        offset += key_length + 2

        (position, promoted_length) = struct.unpack_from(">ql", data, offset)
        offset += 12

        next_offset = offset + promoted_length
        if next_offset < size:
            (key_length,) = struct.unpack_from(">h", data, next_offset)
            next_offset += 2 + key_length
            (next_position,) = struct.unpack_from(">q", data, next_offset)
            partition_size = next_position - position
        else:
            partition_size = -1  # unknown

        if partition_size < args.partition_size_threshold:
            now_reporter = NullReport()
        else:
            now_reporter = reporter

        now_reporter.report_partition_start(
            key, position, promoted_length, partition_size
        )

        if promoted_length:
            (deletion_time, timestamp, entries_count) = struct.unpack_from(
                ">lql", data, offset
            )
            offset += 16

            now_reporter.report_promoted_start(deletion_time, timestamp, entries_count)

            for _ in range(0, entries_count):
                start_length = struct.unpack_from(">h", data, offset)[0]
                start = struct.unpack_from(
                    ">{}s".format(start_length), data, offset + 2
                )[0]
                offset += start_length + 2

                end_length = struct.unpack_from(">h", data, offset)[0]
                end = struct.unpack_from(">{}s".format(end_length), data, offset + 2)[0]
                offset += end_length + 2

                (entry_offset, width) = struct.unpack_from(">qq", data, offset)
                offset += 16

                now_reporter.report_promoted_entry(start, end, entry_offset, width)
        now_reporter.report_partition_end()

    reporter.report_end(partitions)
