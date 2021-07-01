from collections import defaultdict
import unicodedata
from pathlib import Path
from typing import DefaultDict
import re

from lib.functools import get_defaultdict
from lib.settings import load_settings

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
        for glyph, count in results[category]['all']['character'].items():
            if controlcharacter_check(glyph):
                uname, ucat, usubcat = "L", "S", "CC"
            else:
                uname = unicodedata.name(glyph)
                ucat = unicodedata.category(glyph)
                usubcat = uname.split(' ')[0]
            get_defaultdict(results[category]["cat"], ucat[0])
            get_defaultdict(results[category]["cat"][ucat[0]], usubcat)
            get_defaultdict(results[category]["cat"][ucat[0]][usubcat], ucat)
            results[category]["cat"][ucat[0]][usubcat][ucat].update({glyph: count})
    else:
        get_defaultdict(results["combined"], "usr")
        categories = load_settings("settings/evaluate/categories")
        if categories and category in categories.keys():
            get_defaultdict(results["combined"]["usr"], category)
            for glyph, count in results['combined']['all']['character'].items():
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

def missing_unicode(results: DefaultDict, ucd,  profile) -> None:
    """
    Puts the unicode character in user-definied categories
    :param results: results instance
    :param profile: missing unicode profile
    :return:
    """

    get_defaultdict(results["combined"], "missing", list)
    missing_unicodes = load_settings("settings/evaluate/missing_unicode")
    uc_codepoints = set([ord(glyph) for glyph in results['combined']['all']['character'].keys()])
    if missing_unicodes and profile in missing_unicodes.keys():
        get_defaultdict(results["combined"]["missing"], profile, list)
        for subsetting, subvals in missing_unicodes[profile].items():
            #get_defaultdict(results["combined"]["missing"][profile], subsetting, list)
            if subsetting.lower().startswith(('glyph', 'hex', 'codepoint')):
                results["combined"]["missing"][profile][subsetting].extend(set(subvals).difference(uc_codepoints))
            else:
                for subval in subvals:
                    if subsetting.lower().startswith('block'):
                        results["combined"]["missing"][profile][subsetting].extend(
                            set(ucd.block_codepoints(subval)).difference(uc_codepoints))
                    elif subsetting.lower().startswith('script'):
                        results["combined"]["missing"][profile][subsetting].extend(
                            set(ucd.script_codepoints(subval)).difference(uc_codepoints))
                    elif subsetting.lower().startswith('property'):
                        results["combined"]["missing"][profile][subsetting].extend(
                            set(ucd.property_codepoints(subval)).difference(uc_codepoints))
                    elif subsetting.lower().startswith('name'):
                        results["combined"]["missing"][profile][subsetting].extend(
                            set(ucd.name_codepoints(subval, regex='regex' in subsetting.lower())).difference(uc_codepoints))


def validate_with_guidelines(results: DefaultDict, eval) -> None:
    """
    Validates each unicode character against the OCR-D or user-definded guidelines
    :param results: result instance
    :param eval: arguments instance
    :return:
    """
    guideline = eval.guideline
    guidelines = eval.guidelines
    get_defaultdict(results, "guidelines")
    if guidelines and guideline in guidelines.keys():
        for file, fileinfo in results['single'].items():
            text = fileinfo['text']
            for conditionkey, conditions in guidelines[guideline].items():
                for condition in conditions:
                    if "REGEX" in conditionkey.upper():
                        count = re.findall(rf"{condition}", text)
                        if count:
                            get_defaultdict(results["guidelines"], guideline)
                            get_defaultdict(results["guidelines"][guideline], conditionkey, instance=int)
                            results["guidelines"][guideline][conditionkey][condition] += len(count)
                            eval.print(str(file))
                            eval.print(condition)
                            eval.print(text + '\n')
                            if eval.json:
                                get_defaultdict(results['single'][file], 'guideline_violation', instance=int)
                                results['single'][file]['guideline_violation'][condition] += len(count)

                    else:
                        for glyph in text:
                            if controlcharacter_check(glyph):
                                uname = "ControlCharacter"
                            else:
                                uname = unicodedata.name(glyph)
                            if ord(glyph) == condition or \
                                    isinstance(condition, str) and \
                                    condition.upper() in uname:
                                get_defaultdict(results["guidelines"], guideline)
                                get_defaultdict(results["guidelines"][guideline], conditionkey, instance=int)
                                results["guidelines"][guideline][conditionkey][condition] += 1
                                if eval.verbose:
                                    import shutil
                                    fout = Path(f"./output/{file.name}")
                                    if not fout.parent.exists():
                                        fout.parent.mkdir()
                                    fout.open("w").write(text)
                                    #imgname = str(file.name).replace('.gt.txt', '.png')
                                    #shutil.copy(file.parent.joinpath(imgname), Path("./output/"))
                                    eval.print(file)
                                    eval.print(condition if isinstance(condition, str) else chr(condition))
                                    eval.print(text + '\n')
    return
