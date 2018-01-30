
# Author: Skip Montanaro (skip@mojam.com)
# Version: 0.1
# https://github.com/smontanaro/python-bits/blob/master/sylk.py

"""Read SYLK files

Caveat emptor!  This module has only been tested with SYLK files generated
by AppleWorks 5.0!  It almost certainly needs work to be able to process
files generated by other spreadsheets.
"""

import re
import time


class Table:
    """
    Table of rows used to store sylk parsed datas

    rows are compound of a various amount of datas (different length)
    """
    def __init__(self):
        self.rows = []

    def __setitem__(self, xy_tuple, val):
        """
        Setitem method to set datas in this grid

        :param tuple xy_tuple: The x,y coordinates as 2-uple
        :param str val: The value to store in the grid

        Handle the completion of a row to ensure the grid's row is wide enough
        to set the value
        """
        (x, y) = xy_tuple
        ox = x - 1
        oy = y - 1
        # Ensure the table is long enough to store the val
        while len(self.rows) < y:
            new_row = [' '] * x
            self.rows.append(new_row)

        row = self.rows[oy]
        if val not in ('', ' '):
            # Ensure the row is large enough to store the val
            if len(row) < x:
                self._extend_row(row, x - len(row))
            self.rows[oy][ox] = val

    def _extend_row(self, row, missing):
        """
        Extend a row adding void values

        :param list row: a list of datas
        :param int missing: The number of void items to add
        """
        row.extend([' '] * missing)
        return row

    def __iter__(self):
        for row in self.rows:
            yield row


class SYLK:
    """class to read SYLK files and dump to CSV"""

    # when time began
    # different computers use different base dates and store dates as offsets
    # this makes SYLK inherently unportable, but we fudge that by
    # using the ID field to guess at the creating platform
    # note that PCs apparently can't properly decode SYLK files generated
    # on Macs using Appleworks/Clarisworks because they don't take this into
    # account
    unixepoch = (1970, 1, 1, 0, 0, 0, 0, 0, 0)
    macepoch = (1904, 1, 1, 0, 0, 0, 0, 0, 0)
    # this is pure fiction...
    pcepoch = (1900, 1, 1, 0, 0, 0, 0, 0, 0)

    # map SYLK format strings into data types
    knownformats = {
        'General': 'string',
        '0': 'int',
        '0.00': 'float',
        '#,##0': 'int',
        '#,##0.00': 'float',
        '"$"#,##0\ ;;\("$"#,##0\,': 'float',
        '"$"#,##0.00\ ;;\("$"#,##0.00\,': 'float',
        '0%': 'float',
        '0.00%': 'float',
        '0.00E+00': 'float',
        'm/d/yy': 'date',
        'd-mmm-yy': 'date',
        'd-mmm': 'date',
        'mmm-yy': 'date',
        'h:mm AM/PM': 'time',
        'h:mm:ss AM/PM': 'time',
        'h:mm': 'time',
        'h:mm:ss': 'time',
        'hh:mm AM/PM': 'time',
        'hh:mm:ss AM/PM': 'time',
        'h:mm': 'time',
        'h:mm:ss': 'time',
        'm/d/yy h:mm': 'datetime',
        'm-dd-yy': 'date',
        'm-dd': 'date',
        '"$"#,##0 ;;[Red]("$"#,##0,': 'float',
        '"$"#,##0.00 ;;[Red]("$"#,##0.00,': 'float',
        'mmm d, yyyy': 'date',
        'mmmm d, yyyy': 'date',
        'ddd, mmm d, yyyy': 'date',
        'dddd, mmmm d, yyyy': 'date',
        'd, mmmm yyyy': 'date',
    }

    date_output = "%d/%m/%Y"

    def __init__(self):
        self.datebase = self.unixepoch
        self.printformats = []
        self.currentformat = self.currenttype = ""
        self.curx = self.cury = 0
        self.data = Table()
        self.unknown = {}

    def escape(self, s):
        """
        Escape a string
        """
        if s[0:1] == '"':
            return '"' + re.sub('"', '\\"\\"', s[1:-1]) + '"'
        return s

    def parse(self, stream):
        """
        Parse the given stream
        """
        lines = re.sub("[\r\n]+", "\n", stream.read()).split("\n")
        for line in lines:
            self.parseline(line)

    def stream_rows(self):
        """
        Stream the rows (to be used to write a csv file for example)
        """
        return self.data

    def addunknown(self, fld, subfld):
        self.unknown[fld] = self.unknown.get(fld, {})
        self.unknown[fld][subfld] = 1

    def writeunknown(self, stream):
        if self.unknown:
            stream.write("Unrecognized fields (subfields):\n")
            for key in list(self.unknown.keys()):
                stream.write("%s (%s)\n" % (
                    key,
                    repr(list(self.unknown[key].keys())))
                )
        else:
            stream.write("No unrecognized fields\n")
        stream.flush()

    def _id_field(self, fields):
        if fields[1][:6] in ("PClari", "PApple"):
            self.datebase = self.macepoch
        elif fields[1][:6] in ('P Sage',):
            self.datebase = self.pcepoch

    def _f_field(self, fields):
        for f in fields[1:]:
            ftd = f[0]
            val = f[1:]
            if ftd == "X":
                self.curx = int(val)
            elif ftd == "Y":
                self.cury = int(val)
            elif ftd == "P":
                # references print format for the next cell
                self.currentformat, self.currenttype = \
                                    self.printformats[int(val)]
            else:
                self.addunknown("F", ftd)

    def _c_field(self, fields):
        for f in fields[1:]:
            ftd = f[0]
            val = f[1:]
            if ftd == "X":
                self.curx = int(val)

            elif ftd == "Y":
                self.cury = int(val)

            elif ftd == "K":
                val = eval(self.escape(val))
                if type(val) == int:
                    if self.currenttype == "date":
                        # value is offset in days from datebase
                        date = time.localtime(
                            time.mktime(self.datebase) +
                            float(val) * 24 * 60 * 60
                        )

                        val = time.strftime(self.date_output, date)

                self.data[(self.curx, self.cury)] = "%s" % val

            else:
                self.addunknown("C", ftd)

    def _p_fields(self, fields):
        if fields[1][0] == "P":
            # print formats imply data types?
            format = fields[1][1:].replace("\\", "")
            if format in self.knownformats:
                self.printformats.append(
                    (
                        format,
                        self.knownformats[format]
                    )
                )
            else:
                # hack to guess type...
                hasY = "y" in format
                hasD = "d" in format
                hasH = "h" in format
                hasZ = "0" in format
                hasP = "." in format
                if (hasD or hasY) and hasH:
                    dtype = "datetime"
                elif hasD or hasY:
                    dtype = "date"
                elif hasH:
                    dtype = "time"
                elif hasP and hasZ:
                    dtype = "float"
                elif hasZ:
                    dtype = "int"
                else:
                    dtype = "string"
                self.printformats.append((format, dtype))
        else:
            self.addunknown("P", fields[1][0])

    def parseline(self, line):
        fields = re.split("(?i);(?=[a-z])", line)
        if fields[0] == "ID":
            self._id_field(fields)
        if fields[0] == "F":
            self._f_field(fields)
        elif fields[0] == "C":
            self._c_field(fields)
        elif fields[0] == "P":
            self._p_fields(fields)
        else:
            fld = fields[0]
            for f in fields[1:]:
                self.addunknown(fld, f)

    def __iter__(self):
        return self.data.__iter__()
