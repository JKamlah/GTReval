import re
import unicodedata
from collections import defaultdict
import itertools
from typing import DefaultDict

from lib.functools import get_defaultdict
from lib.settings import load_profiles


def controlcharacter_check(glyph: str):
    """
    Checks if glyph is controlcharacter (unicodedata cant handle CC as input)
    :param glyph: unicode glyph
    :return:
    """
    if len(glyph) == 1 and (ord(glyph) < int(0x001F) or int(0x007F) <= ord(glyph) <= int(0x009F)):
        return True
    else:
        return False


def categorize(results: DefaultDict, category='combined') -> None:
    """
    Puts the unicode character in user-definied categories
    :param results: results instance
    :param category: category
    :return:
    """
    get_defaultdict(results["combined"], "cat")
    if category == 'combined':
        for glyph, count in results[category]['all']['glyph'].items():
            if controlcharacter_check(glyph):
                uname, ucat, usubcat = "L", "S", "CC"
            else:
                try:
                    uname = unicodedata.name(glyph)
                    ucat = unicodedata.category(glyph)
                    usubcat = uname.split(' ')[0]
                except ValueError:
                    uname, ucat, usubcat = "Unknow", "Unknow", "Unknow"
            get_defaultdict(results[category]["cat"], ucat[0])
            get_defaultdict(results[category]["cat"][ucat[0]], usubcat)
            get_defaultdict(results[category]["cat"][ucat[0]][usubcat], ucat)
            results[category]["cat"][ucat[0]][usubcat][ucat].update({glyph: count})
    else:
        get_defaultdict(results["combined"], "usr")
        categories = load_profiles("profiles/evaluate/categories")
        if categories and category in categories.keys():
            get_defaultdict(results["combined"]["usr"], category)
            for glyph, count in results['combined']['all']['glyph'].items():
                for subcat, subkeys in categories[category].items():
                    for subkey in subkeys:
                        if controlcharacter_check(glyph):
                            uname = "ControlCharacter"
                        else:
                            uname = unicodedata.name(glyph)
                        if ord(glyph) == subkey or subkey in uname:
                            get_defaultdict(results["combined"]["usr"][category], subcat)
                            results["combined"]["usr"][category][subcat][glyph] = count
    return


def missing_unicode(results: DefaultDict, evalu, ucd, profile) -> None:
    """
    Puts the unicode character in user-definied categories
    :param results: results instance
    :param evalu: process handler
    :param ucd: unicode handler
    :param profile: missing unicode profile
    :return:
    """
    get_defaultdict(results["combined"], "missing", list)
    missing_unicodes = load_profiles("profiles/evaluate/missing_unicode")
    uc_codepoints = set(results['combined']['all']['codepoints'].keys())
    uc_combinded_glyphs = set(results['combined']['all']['combined glyph'].keys())
    if missing_unicodes and profile in missing_unicodes.keys():
        get_defaultdict(results["combined"]["missing"], profile, list)
        check_unicode(results["combined"]["missing"][profile], missing_unicodes[profile], uc_codepoints,
                      uc_combinded_glyphs, ucd=ucd)
        if not bool([subval for subval in results["combined"]["missing"][profile].values() if subval != []]):
            results["combined"]["missing"][profile] = {f"All glyphs from '{profile}' were found!": []}
    else:
        if profile not in missing_unicodes.keys():
            evalu.print(f"'{profile}' was not found in the settings file")


def difference(fst_set, snd_set):
    return set(fst_set).difference(set(snd_set))


def intersection(fst_set, snd_set):
    return set(fst_set).intersection(set(snd_set))


def check_unicode(resdict, profiles, uc_codepoints, uc_combinded_glyphs, func='difference', ucd=None):
    func = {'difference': difference, 'intersection': intersection}.get(func, difference)
    for subsetting, subvals in profiles.items():
        if subsetting.lower().startswith(('glyph', 'hex', 'codepoint')):
            resdict[subsetting].extend(func(subvals, uc_codepoints))
        elif subsetting.lower().startswith('combined'):
            resdict[subsetting].extend(func(subvals, uc_combinded_glyphs))
        elif ucd:
            for subval in subvals:
                if subsetting.lower().startswith('block'):
                    resdict[subsetting].extend(func(ucd.block_codepoints(subval), uc_codepoints))
                elif subsetting.lower().startswith('script'):
                    resdict[subsetting].extend(func(ucd.script_codepoints(subval), uc_codepoints))
                elif subsetting.lower().startswith('property'):
                    resdict[subsetting].extend(func(ucd.property_codepoints(subval), uc_codepoints))
                elif subsetting.lower().startswith('name'):
                    resdict[subsetting].extend(
                        func(ucd.name_codepoints(subval, regex='regex' in subsetting.lower()), uc_codepoints))
    return


def validate_with_guidelines(results: DefaultDict, evalu) -> None:
    """
    Validates each unicode character against the OCR-D or user-definded guidelines
    :param results: result instance
    :param evalu: arguments instance
    :return:
    """
    guideline = evalu.guideline
    guidelines = evalu.guidelines
    get_defaultdict(results, "guidelines")
    uc_codepoints = set(results['combined']['all']['codepoints'].keys())
    uc_combinded_glyphs = set(results['combined']['all']['combined glyph'].keys())
    if guidelines and guideline in guidelines.keys():
        get_defaultdict(results["guidelines"], guideline)
        for conditionkey, conditions in guidelines[guideline].items():
            for condition in conditions:
                if "regex" in conditionkey.lower():
                    for file, fileinfo in results['single'].items():
                        text = fileinfo['text']
                        count = re.findall(rf"{condition}", text)
                        if count:
                            get_defaultdict(results["guidelines"][guideline], conditionkey, instance=int)
                            results["guidelines"][guideline][conditionkey][condition] += len(count)
                            pid, file = file.split(':', 1)
                            file = str(results['path_indexes'][f"{pid}"].joinpath(file.rsplit('_', 1)[0]))
                            evalu.print(str(file))
                            evalu.print(condition)
                            evalu.print(text + '\n')
                            if evalu.json:
                                get_defaultdict(results['single'][file], 'guideline_violation', instance=int)
                                results['single'][file]['guideline_violation'][condition] += len(count)
                else:
                    violation_codepoints = defaultdict(list)
                    check_unicode(violation_codepoints, guidelines[guideline], uc_codepoints, uc_combinded_glyphs,
                                  func='intersection')
                    violation_codepoint_dict = {
                        violation_codepoint: results['combined']['all']['codepoints'][violation_codepoint] for
                        violation_codepoint in set(itertools.chain.from_iterable(violation_codepoints.values()))}
                    if violation_codepoint_dict:
                        results["guidelines"][guideline][conditionkey].update(violation_codepoint_dict)
                    if evalu.json:
                        for violation_codepoint in results["guidelines"][guideline][conditionkey]:
                            for file, fileinfo in results['single'].items():
                                text = fileinfo['text']
                                if chr(violation_codepoint) in text:
                                    get_defaultdict(results['single'][file], 'guideline_violation', instance=int)
                                    results['single'][file]['guideline_violation'][condition] += text.count(
                                        chr(violation_codepoint))
    return
