#!/usr/bin/env python3
#
# Copyright (C) 2020 ScyllaDB
#
# Author: Raphael S. Carvalho <raphaelsc@scylladb.com>
#
# Inherited murmur3_token from Cassandra's python-driver
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

import os
import subprocess
import sys
import time
import argparse
import struct
import psutil

# WARNING: don't tweak the value below whatsoever as it's a CONSTANT.
deletion_time_for_never_expiring_sstable = 2147483647 # timestamp in seconds

class inclusive_range:
    def __init__(self, first, last):
        self.first = first
        self.last = last

    def overlaps(self, other):
        if not isinstance(other, inclusive_range):
            sys.exit("other is not inclusive_range")
        return self.first <= other.first <= self.last or other.first <= self.first <= other.last

    def fmt(self):
        return str("([{}, {}])".format(self.first, self.last))

class sstable:
    def __init__(self, name, min_timestamp, max_timestamp, max_deletion_time, first_token, last_token):
        self.name = name # name of this sstable
        self.min_timestamp = min_timestamp # in microseconds
        self.max_timestamp = max_timestamp # in microseconds
        self.max_deletion_time = max_deletion_time # in seconds
        self.first_token = first_token
        self.last_token = last_token

    def overlaps_in_token(self, other_range):
        this_range = inclusive_range(self.first_token, self.last_token)
        return this_range.overlaps(other_range)

    def overlaps_in_timestamp(self, other):
        if not isinstance(other, sstable):
            sys.exit("other is not sstable")
        this_range = inclusive_range(self.min_timestamp, self.max_timestamp)
        other_range = inclusive_range(other.min_timestamp, other.max_timestamp)
        return this_range.overlaps(other_range)

    def token_range(self):
        return inclusive_range(self.first_token, self.last_token)

    def fmt(self):
        return str("{}: ts: [{}, {}], max deletion ts: {}, token: [{}, {}]".format(self.name, self.min_timestamp, \
            self.max_timestamp, self.max_deletion_time, self.first_token, self.last_token))

def exit(sst, reason):
    sys.exit("Exiting due to bad metadata retrieved from SSTable {}, reason: {}".format(sst.fmt(), reason))

def sane_timestamp(ts, min_ts, max_ts):
    return ts >= min_ts and ts <= max_ts;

def sanity_check_sstable_metadata(sst, now_in_seconds):
    if sst.min_timestamp == 0:
        exit(sst, "min_timestamp == 0")
    if sst.max_timestamp == 0:
        exit(sst, "max_timestamp == 0")
    if sst.max_deletion_time == 0:
        exit(sst, "max_deletion_time == 0")
    if sst.max_timestamp < sst.min_timestamp:
        exit(sst, "sst.max_timestamp < sst.min_timestamp")
    if not sane_timestamp(sst.max_deletion_time, 1500000000, deletion_time_for_never_expiring_sstable):
        exit(sst, "max_deletion_time not sane")
    if not sane_timestamp(sst.min_timestamp, 1500000000000000, 2000000000000000):
        exit(sst, "min_timestamp not sane")
    if not sane_timestamp(sst.max_timestamp, 1500000000000000, 2000000000000000):
        exit(sst, "max_timestamp not sane")

# constants below belong to class murmur3_token
INT64_MAX = int(2 ** 63 - 1)
INT64_MIN = -INT64_MAX - 1
INT64_OVF_OFFSET = INT64_MAX + 1
INT64_OVF_DIV = 2 * INT64_OVF_OFFSET

class murmur3_token:
    @staticmethod
    def body_and_tail(data):
        l = len(data)
        nblocks = l // 16
        tail = l % 16
        if nblocks:
            # we use '<', specifying little-endian byte order for data bigger than
            # a byte so behavior is the same on little- and big-endian platforms
            return struct.unpack_from('<' + ('qq' * nblocks), data), struct.unpack_from('b' * tail, data, -tail), l
        else:
            return tuple(), struct.unpack_from('b' * tail, data, -tail), l

    @staticmethod
    def rotl64(x, r):
        # note: not a general-purpose function because it leaves the high-order bits intact
        # suitable for this use case without wasting cycles
        mask = 2 ** r - 1
        rotated = (x << r) | ((x >> 64 - r) & mask)
        return rotated

    @staticmethod
    def fmix(k):
        # masking off the 31s bits that would be leftover after >> 33 a 64-bit number
        k ^= (k >> 33) & 0x7fffffff
        k *= 0xff51afd7ed558ccd
        k ^= (k >> 33) & 0x7fffffff
        k *= 0xc4ceb9fe1a85ec53
        k ^= (k >> 33) & 0x7fffffff
        return k

    @staticmethod
    def truncate_int64(x):
        if not INT64_MIN <= x <= INT64_MAX:
            x = (x + INT64_OVF_OFFSET) % INT64_OVF_DIV - INT64_OVF_OFFSET
        return x

    @staticmethod
    def get_token(data):

        h1 = h2 = 0

        c1 = -8663945395140668459  # 0x87c37b91114253d5
        c2 = 0x4cf5ad432745937f

        body, tail, total_len = murmur3_token.body_and_tail(data)

        # body
        for i in range(0, len(body), 2):
            k1 = body[i]
            k2 = body[i + 1]

            k1 *= c1
            k1 = murmur3_token.rotl64(k1, 31)
            k1 *= c2
            h1 ^= k1

            h1 = murmur3_token.rotl64(h1, 27)
            h1 += h2
            h1 = h1 * 5 + 0x52dce729

            k2 *= c2
            k2 = murmur3_token.rotl64(k2, 33)
            k2 *= c1
            h2 ^= k2

            h2 = murmur3_token.rotl64(h2, 31)
            h2 += h1
            h2 = h2 * 5 + 0x38495ab5

        # tail
        k1 = k2 = 0
        len_tail = len(tail)
        if len_tail > 8:
            for i in range(len_tail - 1, 7, -1):
                k2 ^= tail[i] << (i - 8) * 8
            k2 *= c2
            k2 = murmur3_token.rotl64(k2, 33)
            k2 *= c1
            h2 ^= k2

        if len_tail:
            for i in range(min(7, len_tail - 1), -1, -1):
                k1 ^= tail[i] << i * 8
            k1 *= c1
            k1 = murmur3_token.rotl64(k1, 31)
            k1 *= c2
            h1 ^= k1

        # finalization
        h1 ^= total_len
        h2 ^= total_len

        h1 += h2
        h2 += h1

        h1 = murmur3_token.fmix(h1)
        h2 = murmur3_token.fmix(h2)

        h1 += h2

        return murmur3_token.truncate_int64(h1)

def sstable_components():
    return [ "Data.db", "Index.db", "Summary.db", "Filter.db", "Scylla.db", "CompressionInfo.db", "CRC.db", "Statistics.db", "TOC.txt", "Digest.crc32" ]

def validate_component(filename):
    components = sstable_components()
    for component in components:
        if filename.find(component) != -1:
            return component
    sys.exit("No valid component found in the filename {}".format(filename))

def validate_format(filename):
    valid_formats = [ "ka", "la", "mc" ];
    basename = os.path.basename(filename)
    for valid_format in valid_formats:
        if basename.find(valid_format) != -1:
            return valid_format
    sys.exit("Format of this SSTable {} is not supported, supported formats: {}".format(filename, valid_formats))

class sstable_metadata_processor:
    def __init__(self, filename):
        self.min_timestamp = 0
        self.max_timestamp = 0
        self.max_deletion_time = 0
        self.first_token = 0
        self.last_token = 0

        sstable_format = validate_format(filename)
        component = validate_component(filename)

        summary_filename = filename.replace(component, "Summary.db")
        self.first_token, self.last_token = self.get_sstable_tokens(summary_filename)

        statistics_filename = filename.replace(component, "Statistics.db")
        self.init_stats_metadata(statistics_filename, sstable_format)

    def get_sstable_tokens(self, filename):
        try:
            with open(filename, 'rb') as f:
                minIndexInterval = struct.unpack('>I', f.read(4))[0]
                offsetCount = struct.unpack('>I', f.read(4))[0]
                offheapSize = struct.unpack('>q', f.read(8))[0]
                samplingLevel = struct.unpack('>I', f.read(4))[0]
                fullSamplingSummarySize = struct.unpack('>I', f.read(4))[0]
                f.read(offsetCount * 4)
                f.read(offheapSize - offsetCount * 4);
                firstSize = struct.unpack('>I', f.read(4))[0]
                firstString = '>' + str(firstSize) + 's'
                first = struct.unpack(firstString, f.read(firstSize))[0]
                lastSize = struct.unpack('>I', f.read(4))[0]
                lastString = '>' + str(lastSize) + 's'
                last = struct.unpack(lastString, f.read(lastSize))[0]
        except Exception as e:
            print(e)
            sys.exit(1)

        return murmur3_token.get_token(first), murmur3_token.get_token(last)

    def init_stats_metadata(self, filename, sstable_format):
        found_stats = False
        try:
            with open(filename, 'rb') as f:
                count = struct.unpack('>I', f.read(4))[0]
                #print ("Statistics file has %d components" % count)
                for i in range(count):
                    type = struct.unpack('>I', f.read(4))[0]
                    offset = struct.unpack('>I', f.read(4))[0]
                    if type == 2:
                        found_stats = True
                        #print ("Found component 2 (statistics) in position %d" % offset)
                        f.seek(offset)
                        # estimated_histogram estimated_row_size;
                        n = struct.unpack('>I', f.read(4))[0]
                        f.read(8 * 2 * n)
                        # estimated_histogram estimated_column_count;
                        n = struct.unpack('>I', f.read(4))[0]
                        f.read(8 * 2 * n)
                        # replay position
                        f.read(8) # segment_id_type
                        f.read(4) # position_type
                        # int64_t min_timestamp;
                        self.min_timestamp = struct.unpack('>q', f.read(8))[0]
                        # int64_t max_timestamp;
                        self.max_timestamp = struct.unpack('>q', f.read(8))[0]
                        if sstable_format == "mc":
                            # uint32_t min_local_deletion_time;
                            f.read(4)
                        # uint32_t max_local_deletion_time;
                        self.max_deletion_time = struct.unpack('>I', f.read(4))[0]
                        if sstable_format == "mc":
                            # int32_t min_ttl;
                            f.read(4)
                            # int32_t max_ttl;
                            f.read(4)
                        # double compression_ratio;
                        f.read(8)
                        # streaming_histogram estimated_tombstone_drop_time;
                        max_bin_size = struct.unpack('>I', f.read(4))[0]
                            # disk_hash<uint32_t, double, uint64_t> bin
                        n = struct.unpack('>I', f.read(4))[0]
                        f.read((8+8) * n)
                        # uint32_t sstable_level;
                        #pos = f.tell()
                        #print ("sstable level in position %d" % pos)
                        #self.sstable_level = struct.unpack('>I', f.read(4))[0]
                        #print ("Found sstable level %d" % self.sstable_level)
        except Exception as e:
            print(e)
            sys.exit(1)
        if not found_stats:
            sys.exit("Unable to retrieve Stats metadata from {}".format(filename))

def sstable_component_for_identification():
    return "TOC.txt"

def process_sstables(table_path, now_in_seconds):
    sstables = []
    sstable_component = sstable_component_for_identification()
    print("Processing table {}...".format(table_path))
    for entry in os.listdir(table_path):
        entry_path = os.path.join(table_path, entry)
        if not os.path.isfile(entry_path):
            continue
        if not entry.endswith(sstable_component):
            continue

        try:
            metadata = sstable_metadata_processor(entry_path)

            sst = sstable(entry, metadata.min_timestamp, metadata.max_timestamp, metadata.max_deletion_time, metadata.first_token, metadata.last_token)
            sanity_check_sstable_metadata(sst, now_in_seconds)
            sstables.append(sst)
        except Exception as e: 
            sys.exit("Unable to retrieve metadata from {} due to: {}".format(entry_path, e))
    return sstables

def dump_processed_sstables(sstables):
    for sstable in sstables:
        print("Found {}".format(sstable.fmt()))

# convert timestamp in us to second
def timestamp_in_seconds(timestamp):
    return int(round(timestamp / 1000000))

def ignores_max_deletion_time(sstable, ignore_max_deletion_time):
    return ignore_max_deletion_time and sstable.max_deletion_time == deletion_time_for_never_expiring_sstable

def calculate_max_deletion_time(sstable, default_ttl):
    return timestamp_in_seconds(sstable.max_timestamp) + default_ttl

def is_sstable_expired(sstable, gc_before_in_sec, default_ttl, ignore_max_deletion_time):
    max_deletion_time = sstable.max_deletion_time

    if ignores_max_deletion_time(sstable, ignore_max_deletion_time):
        actual_max_deletion_time = calculate_max_deletion_time(sstable, default_ttl)
        print("Ignoring max deletion time of SSTable {}: {} -> {}".format(sstable.name, max_deletion_time, actual_max_deletion_time))
        max_deletion_time = actual_max_deletion_time

    return max_deletion_time < gc_before_in_sec

def find_expired_sstables(sstables, gc_before_in_sec, default_ttl, ignore_max_deletion_time):
    expired_sstables = []
    non_expired_sstables = []
    for sstable in sstables:
        if is_sstable_expired(sstable, gc_before_in_sec, default_ttl, ignore_max_deletion_time):
            expired_sstables.append(sstable)
        else:
            non_expired_sstables.append(sstable)
    return expired_sstables, non_expired_sstables

def dump_expired_sstables(expired_sstables, gc_before_in_sec, default_ttl, ignore_max_deletion_time, table_path):
    expired_ssts_which_ignored_max_deletion_time = []
    
    for sstable in expired_sstables:
        additional = ""
        max_deletion_time = sstable.max_deletion_time
        if ignores_max_deletion_time(sstable, ignore_max_deletion_time):
            additional = " (max deletion time was ignored)"
            max_deletion_time = calculate_max_deletion_time(sstable, default_ttl)
            expired_ssts_which_ignored_max_deletion_time.append(sstable)
        print("Found expired SSTable {}, {} < {}{}".format(sstable.name, max_deletion_time, gc_before_in_sec, additional))

    if len(expired_ssts_which_ignored_max_deletion_time):
        msg = "".join([str(sst.name + ", ") for sst in expired_ssts_which_ignored_max_deletion_time])
        print("Expired SSTables which max deletion time was ignored: [{}]".format(msg))
        print("{}MB of disk space can potentially be reclaimed from expired SSTables which max deletion time was ignored".format(total_space_for_sstables_in_mb(table_path, expired_ssts_which_ignored_max_deletion_time)))

def get_unified_token_range(sstables) :
    first = min(sstables, key=lambda sst: sst.first_token)
    last = max(sstables, key=lambda sst: sst.last_token)
    return inclusive_range(first.first_token, last.last_token)

def find_blockers_for_expired_sstables(expired_sstables, non_expired_sstables):
    expired_ssts_token_range = get_unified_token_range(expired_sstables)
    overlapping_non_expired_ssts = []

    blocked_expired_ssts = []
    non_blocked_expired_ssts = []
    
    for sstable in non_expired_sstables:
        if sstable.overlaps_in_token(expired_ssts_token_range):
            print("SSTable {} overlaps with token range of expired SSTables".format(sstable.name))
            overlapping_non_expired_ssts.append(sstable)
    
    for expired_sst in expired_sstables:
        blockers = str("Blockers for expired SSTable {}: ".format(expired_sst.name))
        found_blocker = False
        for overlapping_non_expired_sst in overlapping_non_expired_ssts:
            # Expired SSTable is blocked if its timestamp range overlaps with the non-expired (overlapping) SSTables
            if expired_sst.overlaps_in_timestamp(overlapping_non_expired_sst):
                blockers += str("{}, ".format(overlapping_non_expired_sst.name))
                # Add expired SST to list of blocked only once
                if not found_blocker:
                    blocked_expired_ssts.append(expired_sst)
                found_blocker = True
        if not found_blocker:
            blockers += str("None")
            non_blocked_expired_ssts.append(expired_sst)
        print(blockers)

    return blocked_expired_ssts, non_blocked_expired_ssts

def exit_if_failed_on_a_non_optional_component(component, error_msg):
    # ignore optional components
    if component != "CompressionInfo.db" and component != "CRC.db" and component != "Digest.crc32":
        sys.exit(error_msg)

def total_space_for_sstables_in_mb(table_path, sstables):
    total = 0
    components = sstable_components()
    sstable_component = sstable_component_for_identification()
    
    for sstable in sstables:
        for component in components:
            f = sstable.name.replace(sstable_component, component)
            try:
                total += os.stat(os.path.join(table_path, f)).st_size
            except:
                exit_if_failed_on_a_non_optional_component(component, "Unabled to read size of {}".format(f))

    return total / (1024 * 1024)

def is_scylla_running():
    for pid in psutil.pids():
        p = psutil.Process(pid)
        if p.name().find("scylla") != -1:
            return True
    return False

def move_non_blocked_expired_ssts_to(table_path, sstables, destination_path):
    components = sstable_components()
    sstable_component = sstable_component_for_identification()

    total = 0
    for sstable in sstables:
        # to make it exception safe:
        # 1) first link all the components into backup dir
        # 2) then delete all the components from the original dir
        print("Moving all components of SSTable {}...".format(sstable.name))
        for component in components:
            f = sstable.name.replace(sstable_component, component)
            try:
                os.link(os.path.join(table_path, f), os.path.join(destination_path, f))
            except:
                exit_if_failed_on_a_non_optional_component(component, "Unabled to link SSTable component {}".format(f))
        for component in components:
            f = sstable.name.replace(sstable_component, component)
            try:
                os.remove(os.path.join(table_path, f))
            except:
                exit_if_failed_on_a_non_optional_component(component, "Unabled to delete SSTable component {}".format(f))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--table', type=str, nargs=1, required=True,
                        help='Absolute path to table dir')
    parser.add_argument('--gc-grace-seconds', type=int, nargs=1, required=True,
                        help='GC grace period in seconds')
    parser.add_argument('--default-ttl', type=int, nargs=1, required=True,
                        help='Default Time to Live in seconds')
    parser.add_argument('--ignore-max-deletion-time', action="store_true",
                        help='Ignore max deletion time of never-expiring SSTable, and assume its TTL == default TTL')
    parser.add_argument('--safely-move-expired-sstables-to', type=str, nargs=1, required=False,
                        help='Specify path to backup dir, at which fully expired SSTables will be safely moved to. WARNING: please guarantee Scylla is not running for safety reasons!')

    args = parser.parse_args()
    table_path = str(args.table[0])
    default_ttl = int(args.default_ttl[0])
    gc_grace_seconds = int(args.gc_grace_seconds[0])
    now_in_seconds = int(time.time())
    ignore_max_deletion_time = bool(args.ignore_max_deletion_time)
    expired_sstables_destination_dir = ""
    if args.safely_move_expired_sstables_to:
        expired_sstables_destination_dir = str(args.safely_move_expired_sstables_to[0])

    # gc grace period in seconds
    gc_before_in_sec = now_in_seconds - gc_grace_seconds

    # sanity checks
    if not os.path.isdir(table_path):
        sys.exit("Unable to find table directory at specified path {}".format(table_path))
    if default_ttl == 0:
        sys.exit("This script likely wants a default TTL > 0")
    if (now_in_seconds == 0):
        sys.exit("now_in_seconds == 0")

    # sanity checks for safe move of expired SSTables
    if len(expired_sstables_destination_dir):
        if is_scylla_running():
            sys.exit("Running Scylla instance detected. The param --safely-move-expired-sstables-to should only be specified when Scylla is not running for safety reasons.")
        if not os.path.isdir(expired_sstables_destination_dir):
            sys.exit("Unable to find directory, which expired SSTables will be moved to, at specified path {}".format(expired_sstables_destination_dir))

    print("Now time in seconds: {}".format(now_in_seconds))
    print("GC period in seconds: {}".format(gc_grace_seconds))
    print("Default TTL in seconds: {}".format(default_ttl))
    print("Ignore max deletion time: {}\n".format(ignore_max_deletion_time))

    sstables = process_sstables(table_path, now_in_seconds)
    dump_processed_sstables(sstables)

    expired_sstables, non_expired_sstables = find_expired_sstables(sstables, gc_before_in_sec, default_ttl, ignore_max_deletion_time)
    dump_expired_sstables(expired_sstables, gc_before_in_sec, default_ttl, ignore_max_deletion_time, table_path)

    print("{}MB of disk space can eventually be reclaimed from all expired SSTables".format(total_space_for_sstables_in_mb(table_path, expired_sstables)))

    if len(expired_sstables):
        blocked_expired_ssts, non_blocked_expired_ssts = find_blockers_for_expired_sstables(expired_sstables, non_expired_sstables)

        # getting the size of all non-blocked expired SSTS first as a sanity check to make sure all components can be found,
        # before they're moved to a directory if a parameter was specified.
        non_blocked_expired_ssts_size = total_space_for_sstables_in_mb(table_path, non_blocked_expired_ssts)
        print("{}MB of disk space can potentially be reclaimed now from expired SSTables with no blockers".format(non_blocked_expired_ssts_size))
        print("{}MB of disk space can eventually be reclaimed from expired SSTables with blockers".format(total_space_for_sstables_in_mb(table_path, blocked_expired_ssts)))

        if len(expired_sstables_destination_dir):
            msg = "".join([str(sst.name + ", ") for sst in non_blocked_expired_ssts])
            print("Expired SSTables with no blockers: [{}]".format(msg))

            move_non_blocked_expired_ssts_to(table_path, non_blocked_expired_ssts, expired_sstables_destination_dir)

            print("{}MB of disk space was reclaimed by moving the expired SSTables with no blockers to the backup directory {}".format(non_blocked_expired_ssts_size, expired_sstables_destination_dir))

main()
