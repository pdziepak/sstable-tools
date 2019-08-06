import struct
import sys


class Stream:
    size = {
        "c": 1,  # char
        "b": 1,  # signed char (int8)
        "B": 1,  # unsigned char (uint8)
        "?": 1,  # bool
        "h": 2,  # short (int16)
        "H": 2,  # unsigned short (uint16)
        "i": 4,  # int (int32)
        "I": 4,  # unsigned int (uint32)
        "l": 4,  # long (int32)
        "l": 4,  # unsigned long (int32)
        "q": 8,  # long long (int64)
        "Q": 8,  # unsigned long long (uint64)
        "f": 4,  # float
        "d": 8,  # double
    }

    def __init__(self, data, offset=0):
        self.data = data
        self.offset = offset

    def read(self, typ):
        try:
            (val,) = struct.unpack_from(">{}".format(typ), self.data, self.offset)
        except Exception as e:
            raise ValueError(
                "Failed to read type `{}' from stream at offset {}: {}".format(
                    typ, e, self.offset
                )
            )
        self.offset += self.size[typ]
        return val

    def bool(self):
        return self.read("?")

    def int8(self):
        return self.read("b")

    def uint8(self):
        return self.read("B")

    def int16(self):
        return self.read("h")

    def uint16(self):
        return self.read("H")

    def int32(self):
        return self.read("i")

    def uint32(self):
        return self.read("I")

    def int64(self):
        return self.read("q")

    def uint64(self):
        return self.read("Q")

    def float(self):
        return self.read("f")

    def double(self):
        return self.read("d")

    def bytes16(self):
        len = self.int16()
        val = self.data[self.offset : self.offset + len]
        self.offset += len
        return val

    def string16(self):
        buf = self.bytes16()
        try:
            return buf.decode("utf-8")
        except UnicodeDecodeError:
            # FIXME why are some strings unintelligible?
            # FIXME Remove this when we finally transition to Python3
            if sys.version_info[0] == 2:
                return "INVALID(size={}, bytes={})".format(
                    len(buf), "".join(map(lambda x: "{:02x}".format(ord(x)), buf))
                )
            else:
                return "INVALID(size={}, bytes={})".format(
                    len(buf), "".join(map(lambda x: "{:02x}".format(x), buf))
                )

    def map16(self, keytype=string16, valuetype=string16):
        return {self.keytype(): self.valuetype() for _ in range(self.int16())}

    def map32(self, keytype=string16, valuetype=string16):
        return {keytype(self): valuetype(self) for _ in range(self.int32())}

    def array32(self, valuetype):
        return [valuetype(self) for _ in range(self.int32())]

    def tuple(self, *member_types):
        return (mt(self) for mt in member_types)

    def struct(self, *members):
        return {member_name: member_type(self) for member_name, member_type in members}

    @staticmethod
    def instantiate(template_type, *args):
        def instanciated_type(stream):
            return template_type(stream, *args)

        return instanciated_type


def parse(stream, schema):
    return {name: typ(stream) for name, typ in schema}
