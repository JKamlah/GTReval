''''
MIT License

Copyright (c) 2018 Leonides T. Saguisag, Jr.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

import codecs
import ftplib
import os
import re
import struct
import sys
import zipfile
from collections import defaultdict, namedtuple
from fractions import Fraction

from lib.io import app_path

def preservesurrogates(s):
    """
    Function for splitting a string into a list of characters, preserving surrogate pairs.
    In python 2, unicode characters above 0x10000 are stored as surrogate pairs.  For example, the Unicode character
    u"\U0001e900" is stored as the surrogate pair u"\ud83a\udd00":
    s = u"AB\U0001e900CD"
    len(s) -> 6
    list(s) -> [u'A', u'B', u'\ud83a', u'\udd00', u'C', 'D']
    len(preservesurrogates(s)) -> 5
    list(preservesurrogates(s)) -> [u'A', u'B', u'\U0001e900', u'C', u'D']
    :param s: String to split
    :return: List of characters
    """
    #: Ranges of surrogate pairs
    high_surrogate_start = u"\ud800"
    high_surrogate_end = u"\udbff"
    low_surrogate_start = u"\udc00"
    low_surrogate_end = u"\udfff"
    # if not isinstance(s, six.text_type):
    #     raise TypeError(u"String to split must be of type 'unicode'!")
    surrogates_regex_str = u"[{0}-{1}][{2}-{3}]".format(high_surrogate_start,
                                                        high_surrogate_end,
                                                        low_surrogate_start,
                                                        low_surrogate_end)
    surrogates_regex = re.compile(u"(?:{0})|.".format(surrogates_regex_str))
    return surrogates_regex.findall(s)


def _unichr(i):
    """
    Helper function for taking a Unicode scalar value and returning a Unicode character.
    :param i: Unicode scalar value to convert.
    :return: Unicode character
    """
    if not isinstance(i, int):
        raise TypeError
    try:
        return chr(i)
    except ValueError:
        # Workaround the error "ValueError: unichr() arg not in range(0x10000) (narrow Python build)"
        return struct.pack('i', i).decode('utf-32')


def _hexstr_to_unichr(s):
    """
    Helper function for taking a hex string and returning a Unicode character.
    :param s: hex string to convert
    :return: Unicode character
    """
    return _unichr(int(s, 16))


def _padded_hex(i, pad_width=4, uppercase=True):
    """
    Helper function for taking an integer and returning a hex string.  The string will be padded on the left with zeroes
    until the string is of the specified width.  For example:
    _padded_hex(31, pad_width=4, uppercase=True) -> "001F"
    :param i: integer to convert to a hex string
    :param pad_width: (int specifying the minimum width of the output string.
    String will be padded on the left with '0' as needed.
    :param uppercase: Boolean indicating if we should use uppercase characters in the output string (default=True).
    :return: Hex string representation of the input integer.
    """
    result = hex(i)[2:]  # Remove the leading "0x"
    if uppercase:
        result = result.upper()
    return result.zfill(pad_width)


def _uax44lm2transform(s):
    """
    Helper function for taking a string (i.e. a Unicode character name) and transforming it via UAX44-LM2 loose matching
    rule.  For more information, see <https://www.unicode.org/reports/tr44/#UAX44-LM2>.
    The rule is defined as follows:
    "UAX44-LM2. Ignore case, whitespace, underscore ('_'), and all medial hyphens except the hyphen in
    U+1180 HANGUL JUNGSEONG O-E."
    Therefore, correctly implementing the rule involves performing the following three operations, in order:
    1. remove all medial hyphens (except the medial hyphen in the name for U+1180)
    2. remove all whitespace and underscore characters
    3. apply toLowercase() to both strings
    A "medial hyphen" is defined as follows (quoted from the above referenced web page):
    "In this rule 'medial hyphen' is to be construed as a hyphen occurring immediately between two letters in the
    normative Unicode character name, as published in the Unicode names list, and not to any hyphen that may transiently
    occur medially as a result of removing whitespace before removing hyphens in a particular implementation of
    matching. Thus the hyphen in the name U+10089 LINEAR B IDEOGRAM B107M HE-GOAT is medial, and should be ignored in
    loose matching, but the hyphen in the name U+0F39 TIBETAN MARK TSA -PHRU is not medial, and should not be ignored in
    loose matching."
    :param s: String to transform
    :return: String transformed per UAX44-LM2 loose matching rule.
    """
    result = s

    # For the regex, we are using lookaround assertions to verify that there is a word character immediately before (the
    # lookbehind assertion (?<=\w)) and immediately after (the lookahead assertion (?=\w)) the hyphen, per the "medial
    # hyphen" definition that it is a hyphen occurring immediately between two letters.
    medialhyphen = re.compile(r"(?<=\w)-(?=\w)")
    whitespaceunderscore = re.compile(r"[\s_]", re.UNICODE)

    # Ok to hard code, this name should never change: https://www.unicode.org/policies/stability_policy.html#Name
    if result != "HANGUL JUNGSEONG O-E":
        result = medialhyphen.sub('', result)
    result = whitespaceunderscore.sub('', result)
    return result.lower()


#: Documentation on the fields of UnicodeData.txt:
#: https://www.unicode.org/L2/L1999/UnicodeData.html
#: https://www.unicode.org/reports/tr44/#UnicodeData.txt
UnicodeCharacter = namedtuple('UnicodeCharacter', ['code', 'name', 'category', 'combining', 'bidi', 'decomposition',
                                                   'decimal', 'digit', 'numeric', 'mirrored', 'unicode_1_name',
                                                   'iso_comment', 'uppercase', 'lowercase', 'titlecase'])


def load_ucd(update=False):
    import pickle
    # return UnicodeData()
    ucd_picklepath = app_path().joinpath('profiles/evaluate/UCD/ucd.pickle')
    if ucd_picklepath.exists() and not update:
        with open(ucd_picklepath, 'rb') as fin:
            ucd = pickle.load(fin)
    else:
        ucd = UnicodeData()
        with open(ucd_picklepath, 'wb') as fout:
            pickle.dump(ucd, fout)
    return ucd


class UnicodeData:
    """Class for encapsulating the data in UnicodeData.txt"""

    def __init__(self):
        """Initialize the class by building the Unicode character database."""
        self._unicode_character_database = {}
        self._name_codepoint_database = {}
        self._unicode_blocks = defaultdict(list)
        self._load_unicode_block_info()
        self._unicode_scripts = defaultdict(list)
        self._load_unicode_script_info()
        self._unicode_properties = defaultdict(list)
        self._load_unicode_property_info()
        self._build_unicode_character_database()

    def _build_unicode_character_database(self):
        """
        Function for parsing the Unicode character data from the Unicode Character
        Database (UCD) and generating a lookup table.  For more info on the UCD,
        see the following website: https://www.unicode.org/ucd/
        """
        filename = 'UnicodeData.txt'
        current_dir = app_path().joinpath('profiles/evaluate/UCD/')
        tag = re.compile(r"<\w+?>")
        start = '0x0000'
        with codecs.open(current_dir.joinpath(filename), mode='r', encoding='utf-8') as fp:
            for line in fp:
                if not line.strip():
                    continue
                data = line.strip().split(';')
                # Replace the start/end range markers with their proper derived names.
                if data[1].endswith(u"First>"):
                    start = (int(data[0], 16))
                    continue
                elif data[1].endswith(u"Last>"):
                    uc_range = range(start, (int(data[0], 16)))
                else:
                    uc_range = [(int(data[0], 16))]
                    # else:  # Others should use naming rule NR2
                    #    data[1] += data[0]
                for uc_value in uc_range:
                    data[3] = int(data[3])  # Convert the Canonical Combining Class value into an int.
                    if data[5]:  # Convert the contents of the decomposition into characters, preserving tag info.
                        data[5] = u" ".join([_hexstr_to_unichr(s) if not tag.match(s) else s for s in data[5].split()])
                    for i in [6, 7, 8]:  # Convert the decimal, digit and numeric fields to either ints or fractions.
                        if data[i]:
                            if '/' in data[i]:
                                data[i] = Fraction(data[i])
                            else:
                                data[i] = int(data[i])
                    for i in [12, 13, 14]:  # Convert the uppercase, lowercase and titlecase fields to characters.
                        if data[i]:
                            data[i] = _hexstr_to_unichr(data[i])
                    uc_data = UnicodeCharacter(u"U+" + data[0], *data[1:])
                    self._unicode_character_database[uc_value] = uc_data
                    self._name_codepoint_database[str(data[1])] = uc_value

    # @lru_cache() TODO: Do we need caching here?
    def name_codepoints(self, search, regex=False, exactmatch=False):
        if regex:
            try:
                return [self._name_codepoint_database[name] for name in self._name_codepoint_database.keys() if
                        re.match(rf"{search}", name)]
            except:
                return []
        if exactmatch:
            return [self._name_codepoint_database[name] for name in self._name_codepoint_database.keys() if
                    search.strip().lower() == name.lower()]
        else:
            return [self._name_codepoint_database[name] for name in self._name_codepoint_database.keys() if
                    search.strip().lower() in name.lower()]

    def block_codepoints(self, block):
        return self._unicode_blocks.get(block, [])

    def script_codepoints(self, script):
        return self._unicode_scripts.get(script, [])

    def property_codepoints(self, uc_property):
        return self._unicode_properties.get(uc_property, [])

    def get(self, value):
        """
        Function for retrieving the UnicodeCharacter associated with the specified Unicode scalar value.
        :param value: Unicode scalar value to look up.
        :return: UnicodeCharacter instance with data associated with the specified value.
        """
        return self.__getitem__(value)

    def __getitem__(self, item):
        """
        Function for retrieving the UnicodeCharacter associated with the specified Unicode scalar value.
        :param item: Unicode scalar value to look up.
        :return: UnicodeCharacter instance with data associated with the specified value.
        """
        return self._unicode_character_database.__getitem__(item)

    def __iter__(self):
        """Function for iterating through the keys of the data."""
        return self._unicode_character_database.__iter__()

    def __len__(self):
        """Function for returning the size of the data."""
        return self._unicode_character_database.__len__()

    def items(self):
        """
        Returns a list of the data's (key, value) pairs, as tuples.
        :return: list of (key, value) pairs, as tuples.
        """
        return self._unicode_character_database.items()

    def keys(self):
        """
        Returns a list of the data's keys.
        :return: list of the data's keys
        """
        return self._unicode_character_database.keys()

    def values(self):
        """
        Returns a list of the data's values.
        :return: list of the data's values.
        """
        return self._unicode_character_database.values()

    def lookup_by_char(self, c):
        """
        Function for retrieving the UnicodeCharacter associated with the specified Unicode character.
        :param c: Unicode character to look up.
        :return: UnicodeCharacter instance with data associated with the specified Unicode character.
        """
        return self._unicode_character_database[c]

    def lookup_by_name(self, name):
        """
        Function for retrieving the UnicodeCharacter associated with a name.  The name lookup uses the loose matching
        rule UAX44-LM2 for loose matching.  See the following for more info:
        https://www.unicode.org/reports/tr44/#UAX44-LM2
        For example:
        ucd = UnicodeData()
        ucd.lookup_by_name("LATIN SMALL LETTER SHARP S") -> UnicodeCharacter(name='LATIN SMALL LETTER SHARP S',...)
        ucd.lookup_by_name("latin_small_letter_sharp_s") -> UnicodeCharacter(name='LATIN SMALL LETTER SHARP S',...)
        :param name: Name of the character to look up.
        :return: UnicodeCharacter instance with data associated with the character.
        """
        try:
            return self._unicode_character_database[self._name_codepoint_database[_uax44lm2transform(name)]]
        except KeyError:
            raise KeyError(u"Unknown character name: '{0}'!".format(name))

    def _load_unicode_block_info(self):
        """
        Function for parsing the Unicode block info from the Unicode Character
        Database (UCD) and generating a lookup table.  For more info on the UCD,
        see the following website: https://www.unicode.org/ucd/
        """
        filename = "Blocks.txt"
        current_dir = app_path().joinpath('profiles/evaluate/UCD/')
        with codecs.open(current_dir.joinpath(filename), mode='r', encoding='utf-8') as fp:
            for line in fp:
                if not line.strip() or line.startswith('#'):
                    continue  # Skip empty lines or lines that are comments (comments start with '#')
                # Format: Start Code..End Code; Block Name
                block_range, block_name = line.strip().split(';')
                start_range, end_range = block_range.strip().split('..')
                # self._unicode_blocks[range(int(start_range, 16), int(end_range, 16) + 1)] = block_name.strip()
                self._unicode_blocks[block_name.strip()].extend(
                    list(range(int(start_range, 16), int(end_range, 16) + 1)))

    def _load_unicode_script_info(self):
        """
        Function for parsing the Unicode script info from the Unicode Character
        Database (UCD) and generating a lookup table.  For more info on the UCD,
        see the following website: https://www.unicode.org/ucd/
        """
        current_dir = app_path().joinpath('profiles/evaluate/UCD/')
        for scriptfile in ['Scripts.txt', 'ScriptExtensions.txt']:
            with codecs.open(current_dir.joinpath(scriptfile), mode='r', encoding='utf-8') as fp:
                for line in fp:
                    if not line.strip() or line.startswith('#'):
                        continue  # Skip empty lines or lines that are comments (comments start with '#')
                    # Format: Start Code..End Code; Script Name
                    script_range, script_name = line.strip().split(';')
                    script_name = script_name.split('#')[0].strip()
                    if '..' in script_range:
                        start_range, end_range = script_range.strip().split('..')
                    else:
                        start_range, end_range = script_range.strip(), script_range.strip()
                    # self._unicode_scripts[range(int(start_range, 16), int(end_range, 16) + 1)] = script_name.strip()
                    self._unicode_scripts[script_name.strip()].extend(
                        list(range(int(start_range, 16), int(end_range, 16) + 1)))

    def _load_unicode_property_info(self):
        """
        Function for parsing the Unicode property info from the Unicode Character
        Database (UCD) and generating a lookup table.  For more info on the UCD,
        see the following website: https://www.unicode.org/ucd/
        """
        filename = 'PropList.txt'
        current_dir = app_path().joinpath('profiles/evaluate/UCD/')
        with codecs.open(current_dir.joinpath(filename), mode='r', encoding='utf-8') as fp:
            for line in fp:
                if not line.strip() or line.startswith('#'):
                    continue  # Skip empty lines or lines that are comments (comments start with '#')
                # Format: Start Code..End Code; Property Name
                property_range, property_name = line.strip().split(';')
                property_name = property_name.split('#')[0].strip()
                if '..' in property_range:
                    start_range, end_range = property_range.strip().split('..')
                else:
                    start_range, end_range = property_range.strip(), property_range.strip()
                # self._unicode_properties[range(int(start_range, 16), int(end_range, 16) + 1)] = property_name.strip()
                self._unicode_properties[property_name.replace('_', ' ').strip()].append(
                    range(int(start_range, 16), int(end_range, 16) + 1))

    def lookup_by_partial_name(self, partial_name):
        """
        Similar to lookup_by_name(name), this method uses loose matching rule UAX44-LM2 to attempt to find the
        UnicodeCharacter associated with a name.  However, it attempts to permit even looser matching by doing a
        substring search instead of a simple match.  This method will return a generator that yields instances of
        UnicodeCharacter where the partial_name passed in is a substring of the full name.
        For example:
        >> ucd = UnicodeData()
        >> for data in ucd.lookup_by_partial_name("SHARP S"):
        >>     print(data.code + " " + data.name)
        >>
        >> U+00DF LATIN SMALL LETTER SHARP S
        >> U+1E9E LATIN CAPITAL LETTER SHARP S
        >> U+266F MUSIC SHARP SIGN
        :param partial_name: Partial name of the character to look up.
        :return: Generator that yields instances of UnicodeCharacter.
        """
        for k, v in self._name_codepoint_database.items():
            if _uax44lm2transform(partial_name) in k:
                yield self._unicode_character_database[v]


def update_ucd(version=None):
    ftp_server = 'ftp.unicode.org'
    remote_path = '/Public/UCD/latest/ucd/'
    with ftplib.FTP(ftp_server) as ftp:
        ftp.login()  # Anonymous login
        if version and re.match(r'\d+\.\d+\.\d+', version):
            ftp.cwd('/Public/' + version + '/ucd/')
        elif not version:
            ftp.cwd(remote_path)
        else:
            print("Please provide a valid verionnumber i.e. 14.0.0")
        for zip_filename in [filename for filename in ftp.nlst() if filename.lower().endswith('zip')]:
            block_size = 4096
            with open(zip_filename, 'wb') as dest_file_obj:
                print("Starting download: {0}".format(zip_filename))
                ftp.retrbinary("RETR " + zip_filename, dest_file_obj.write, block_size)
                print("Finished downloading: {0}".format(zip_filename))
            print("Testing zip file: {0}".format(zip_filename))
            test_result = zipfile.is_zipfile(zip_filename)
            if not test_result:
                print("Error, invalid zip file: {0}".format(zip_filename))
                print("Exiting...")
                sys.exit(1)
            zip_file = zipfile.ZipFile(zip_filename)
            test_result = zip_file.testzip()
            if test_result:
                print("Error, the following entry is corrupt: {0}".format(test_result))
                print("Exiting...")
                sys.exit(1)
            else:
                print("Successfully tested zip file: {0}".format(zip_filename) + os.linesep)
