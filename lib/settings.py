from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from lib.functools import get_defaultdict


@lru_cache()
def load_profiles(fname: str):
    """
    Loads the profiles into a dict
    :param fname: name of the profile file
    :return:
    """
    settings = defaultdict(dict)
    setting, subsetting = None, None
    mode, submode = fname.split('/')[1:3]
    with open(Path(fname), 'r') as fin:
        for line in fin.readlines():
            line = line.strip()
            if len(line) < 1 or line[0] == '#':
                continue
            if line[0] + line[-1] == '[]':
                setting = line.strip('[]')
                if mode == 'revaluate':
                    get_defaultdict(settings, setting, instance=dict)
                else:
                    get_defaultdict(settings, setting, instance=list)
                continue
            if '==' in line:
                subsetting, line = [part.strip() for part in line.split("==")]
                line = line.strip()
            if setting and mode == 'revaluate':
                get_defaultdict(settings[setting], subsetting, instance=list)  # TODO: Check if it still works
                if subsetting and isinstance(settings[setting][subsetting], dict):
                    lines = [line]
                    if '<-->' in line:
                        parts = line.split('<-->')
                        lines = [parts[0] + '-->' + parts[1], parts[1] + '-->' + parts[0]]
                    for line in lines:
                        orig, values = [part.strip() for part in line.split('-->')]
                        for value in values.split('||'):
                            if '<--' in value:
                                sub, rep = value.split('<--')[:2]
                                settings[setting][subsetting]["<--"] = {orig: rep.strip()}
                            value = value.strip()
                            settings[setting][subsetting][orig].append(read_subsettings(subsetting, value))
            elif setting:
                if subsetting and isinstance(settings[setting][subsetting], list):
                    for value in line.split('||'):
                        value = value.strip()
                        settings[setting][subsetting].extend(read_subsettings(subsetting, value))

        if setting and subsetting:
            return settings


def read_subsettings(subsetting, value):
    if 'regex' in subsetting.lower():
        return [value]
    if subsetting.lower().startswith('unicode'):
        if '-' in value and len(value) > 1 and len(value.split('-')) == 2:
            return [range(*sorted([int(val) if '0x' not in val else int(val, 16) for val in value.split('-')]))]
        else:
            if len(value) == 1:
                return [ord(value)]
            elif value.startswith('0x'):
                return [int(value, 16)]
            else:
                return [value]
    if subsetting.lower().startswith('combined'):
        if len(value) == 2:
            return [value]
    if subsetting.lower().startswith('glyph'):
        if '-' in value and len(value) > 1 and len(value.split('-')) == 2:
            return list(range(*[ord(val) for val in value.split('-')]))
        else:
            return [ord(value)]
    elif subsetting.lower().startswith('hex'):
        if '-' in value and len(value) > 1 and len(value.split('-')) == 2:
            start, end = value.split('-')
            if start.strip().startswith('0x') and end.strip().startswith('0x'):
                return list(range(int(start.strip(), 16), int(end.strip(), 16)))
        else:
            return [int(value, 16)]
    elif subsetting.lower().startswith('codepoint'):
        if '-' in value and len(value) > 1 and len(value.split('-')) == 2:
            start, end = value.split('-')
            if start.isdigit() and end.isdigit():
                return list(range(int(start.strip()), int(end.strip())))
        else:
            return [int(value)]
    else:
        return [value]
