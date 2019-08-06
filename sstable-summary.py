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
cmdline_parser.add_argument("summary_file", help="summary file to parse")

args = cmdline_parser.parse_args()

f = open(args.summary_file, "rb")
data = f.read()
f.close()

offset = 0

(
    min_interval,
    entries_count,
    entries_size,
    sampling_level,
    size_at_full_sampling,
) = struct.unpack_from(">llqll", data)
header_size = 24

print("Minimal interval:\t{}".format(min_interval))
print("Number of entires:\t{}".format(entries_count))
print("Summary entries size:\t{}".format(entries_size))
print("Sampling level:\t\t{}".format(sampling_level))
print("Size at full sampling:\t{}".format(size_at_full_sampling))

positions = list(struct.unpack_from("<{}l".format(entries_count), data, header_size))
positions.append(entries_size)

offset = header_size + entries_size

start_length = struct.unpack_from(">l", data, offset)[0]
start = struct.unpack_from(">{}s".format(start_length), data, offset + 4)[0]
offset += start_length + 4

end_length = struct.unpack_from(">l", data, offset)[0]
end = struct.unpack_from(">{}s".format(end_length), data, offset + 4)[0]
offset += end_length + 4

print("First key:\t\t{}".format(binascii.hexlify(start)))
print("Last key:\t\t{}".format(binascii.hexlify(end)))
print("Total summary size:\t{}".format(offset))
print("Entries:")

for i in range(0, entries_count):
    start = positions[i]
    end = positions[i + 1] - 8

    (key, position) = struct.unpack_from(
        "<{}sq".format(end - start), data, header_size + start
    )

    print("\tKey {} at position {}".format(binascii.hexlify(key), position))
