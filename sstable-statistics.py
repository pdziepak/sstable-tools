#!/usr/bin/env python3

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
