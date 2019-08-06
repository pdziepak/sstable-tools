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
import json
import sstable_tools.statistics


cmdline_parser = argparse.ArgumentParser()
cmdline_parser.add_argument("stats_file", help="stats file to parse")
cmdline_parser.add_argument(
    "-f", "--format", choices=["ka", "la", "mc"], default="mc", help="sstable format"
)

args = cmdline_parser.parse_args()

with open(args.stats_file, "rb") as f:
    data = f.read()

metadata = sstable_tools.statistics.parse(data, args.format)

print(json.dumps(metadata, indent=4))
