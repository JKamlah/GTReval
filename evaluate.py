#!/usr/bin/env python3

import argparse
import io
import json
import re
import sys
import unicodedata
from collections import defaultdict, Counter, OrderedDict
from pathlib import Path
from typing import DefaultDict, Dict

# Command line arguments.
arg_parser = argparse.ArgumentParser(description='Evaluate the ground truth texts for the given text files.')
arg_parser.add_argument("fname", type=lambda x: Path(x), help="filename of text file or path to files", nargs='*')
arg_parser.add_argument("-o", "--output", type=lambda x: Path(x) if x is not None else None, default=None,
                        help="filename of the output report, \
                        if none is given the result is printed to stdout")
arg_parser.add_argument("-j", "--json",
                        help="will also output the all results as json file (including the guideline_violations)",
                        action="store_true")
arg_parser.add_argument("-n", "--dry-run", help="show which files would be normalized but don't change them",
                        action="store_true")
arg_parser.add_argument("-f", "--form", help="normalization form (default: NFC)",
                        choices=["NFC", "NFKC", "NFD", "NFKD"], default="NFC")
arg_parser.add_argument("-c", "--categorize", help="Customized unicodedata categories", type=str,
                        default=["Good Practice"],
                        nargs='*')
arg_parser.add_argument("-s", "--statistical-categories",
                        help="Customized unicodedata categories. 'all' prints information about all unicode character ordered by occurence.",
                        default=["all"], choices=["L", "M", "N", "P", "S", "Z", "C", "all"],
                        nargs='*')
arg_parser.add_argument("-a", "--addinfo", help="Add information, such as unicode name and/or code to output",
                        default=["name"], choices=["name", "code"], nargs='+')
arg_parser.add_argument("-g", "--guidelines", help="Evaluated the dataset against some guidelines", type=str,
                        default="OCRD-1", choices=["OCRD-1", "OCRD-2", "OCRD-3"])
arg_parser.add_argument("-t", "--textnormalization", help="Textnormalization settings", type=str, default="NFC",
                        choices=["NFC", "NFKC", "NFD", "NFKD"])
arg_parser.add_argument("-v", "--verbose", help="show ignored files", action="store_true")

args = arg_parser.parse_args()


def get_defaultdict(resultslvl: Dict, newlvl, instance=OrderedDict) -> None:
    """
    Creates a new dictionary instance into another
    :param resultslvl: instance of the current level
    :param newlvl: name of the new  level
    :param instance: type of the defaultdict instance
    :return:
    """
    resultslvl[newlvl] = defaultdict(instance) if not resultslvl.get(newlvl, None) else resultslvl[newlvl]
    return


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


def load_settings(fname: str) -> DefaultDict:
    """
    Loads the settings file into a dict
    :param fname: name of the settings file
    :return:
    """
    settings = defaultdict(dict)
    setting, subsetting = None, None
    with open(Path(fname), 'r') as fin:
        for line in fin.readlines():
            line = line.strip()
            if len(line) < 1 or line[0] == '#': continue
            if line[0] + line[-1] == '[]':
                setting = line.strip('[]')
                get_defaultdict(settings, setting, instance=list)
                continue
            if setting:
                if '==' in line:
                    subsetting, line = line.split("==")
                    line = line.strip()
                if subsetting and isinstance(settings[setting][subsetting], list):
                    for values in line.split('||'):
                        values = values.strip()
                        if 'regex' in subsetting.lower():
                            settings[setting][subsetting].append(values)
                        elif '-' in values and len(values.split('-')) == 2:
                            settings[setting][subsetting].append(range(
                                *sorted([int(val) if not '0x' in val else int(val, 16) for val in values.split('-')])))
                        elif '-' not in values:
                            if values.isdigit():
                                settings[setting][subsetting].append(int(values))
                            elif values[:2] == '0x':
                                settings[setting][subsetting].append(int(values, 16))
                            elif len(values) > 1:
                                settings[setting][subsetting].append(values)
                            else:
                                settings[setting][subsetting].append(ord(values))
        if setting and subsetting:
            return settings
    return settings


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
        categories = load_settings("settings/analyse/categories")
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


def validate_with_guidelines(results: DefaultDict, args) -> None:
    """
    Validates each unicode character against the OCR-D or user-definded guidelines
    :param results: result instance
    :param args: arguments instance
    :return:
    """
    guideline = args.guidelines
    guidelines = load_settings("settings/analyse/guidelines")
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
                            if args.verbose:
                                print(file)
                                print(condition)
                                print(text + '\n')
                            if args.json:
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
                                if args.verbose:
                                    import shutil
                                    fout = Path(f"./output/{file.name}")
                                    if not fout.parent.exists():
                                        fout.parent.mkdir()
                                    fout.open("w").write(text)
                                    imgname = str(file.name).replace('.gt.txt', '.png')
                                    shutil.copy(file.parent.joinpath(imgname), Path("./output/"))
                                    print(file)
                                    print(condition if isinstance(condition, str) else chr(condition))
                                    print(text + '\n')
    return


def print_unicodeinfo(args, val: str, key: str) -> str:
    """
    Prints the occurrence, unicode character or guideline rules and additional information
    :param args: arguments instance
    :param val: count of the occurrences of key
    :param key: key (glyph or guideline rules)
    :return:
    """
    return f"{val:-{6}}  {'{'}{repr(key) if controlcharacter_check(key) else key}{'}'}{addinfo(args, key)}"


def addinfo(args, key) -> str:
    """
    Adds info to the single unicode statistics like the hexa code or the unicodename
    :param args: arguments instance
    :param key: key string (glyphs or guideline rules)
    :return:
    """
    info = " "
    if len(key) > 1 or controlcharacter_check(key): return ""
    if "code" in args.addinfo:
        info += str(hex(ord(key))) + " "
    if "name" in args.addinfo:
        info += unicodedata.name(key)
    return info.rstrip()


def report_subsection(fout, subsection: str, result: DefaultDict, header="", subheaderinfo="") -> None:
    """
    Creats subsection reports
    :param fout: name of the outputfile
    :param subsection: name of subsection
    :param result: result instance
    :param header: header info string
    :param subheaderinfo: subheader info string
    :return:
    """
    addline = '\n'
    fout.write(f"""
    {header}
    {subheaderinfo}{addline if subheaderinfo != "" else ""}""")
    if not result:
        fout.write(f"""{"-" * 60}\n""")
        return
    for condition, conditionres in result[subsection].items():
        fout.write(f"""
        {condition}
        {"-" * len(condition)}""")
        for key, val in conditionres.items():
            if isinstance(val, dict):
                fout.write(f"""
            {key}:""")
                for subkey, subval in sorted(val.items()):
                    if isinstance(subkey, int) or len(subkey) == 1:
                        subkey = ord(subkey)
                        fout.write(f"""
                            {print_unicodeinfo(args, subval, subkey)}""")
                    else:
                        fout.write(f"""
                            {print_unicodeinfo(args, subval, chr(subkey))}""")
            else:
                if isinstance(key, int):
                    fout.write(f"""
                        {print_unicodeinfo(args, val, chr(key))}""")
                else:
                    fout.write(f"""
                        {print_unicodeinfo(args, val, key)}""")
    fout.write(f"""
    \n{"-" * 60}\n""")
    return


def sum_statistics(result: DefaultDict, section: str) -> int:
    """
    Sums up all occrurences
    :param result: result instance
    :param section: section to sum
    :return:
    """
    return sum([val for subsection in result[section].values() for val in subsection.values()])


def summerize(results: DefaultDict, category: str) -> None:
    """
    Summarizes the results of multiple input data
    :param results: results instance
    :param category: category
    :return:
    """
    if category in results:
        get_defaultdict(results, "sum")
        results["sum"]["sum"] = results["sum"].get('sum', 0)
        get_defaultdict(results["sum"], category)
        results["sum"][category]["sum"] = 0
        for sectionkey, sectionval in results[category].items():
            get_defaultdict(results["sum"][category], sectionkey)
            results["sum"][category][sectionkey]["sum"] = 0
            if isinstance(list(sectionval.values())[0], dict):
                for subsectionkey, subsectionval in sorted(sectionval.items()):
                    get_defaultdict(results["sum"][category][sectionkey], subsectionkey)
                    intermediate_sum = sum(subsectionval.values())
                    results["sum"][category][sectionkey][subsectionkey]["sum"] = intermediate_sum
                    results["sum"][category][sectionkey]["sum"] += intermediate_sum
                    results["sum"][category]["sum"] += intermediate_sum
                    results["sum"]["sum"] += intermediate_sum
            else:
                intermediate_sum = sum(sectionval.values())
                results["sum"][category][sectionkey]["sum"] = intermediate_sum
                results["sum"][category]["sum"] += intermediate_sum
                results["sum"]["sum"] += intermediate_sum
    return


def get_nested_val(ndict, keys, default=0):
    """
    Returns a value or the default value for a key in a nested dictionary
    :param ndict: nested dict instance
    :param keys: keys
    :param default: default value
    :return:
    """
    # TODO: Maybe it is faster with try (ndict[allkeys]) and except (default)..
    val = default
    for key in keys:
        val = ndict.get(key, default)
        if isinstance(val, dict):
            ndict = val
        elif val == 0:
            return val
    return val


def create_report(result: DefaultDict, output: str) -> None:
    """
    Creates the report
    :param result: results instance
    :param output: output string
    :return:
    """
    fpoint = 10
    fnames = "; ".join(set([str(fname.resolve().parent) for fname in args.fname]))
    if not output:
        fout = sys.stdout
        if not args.verbose:
            fnames = args.orig_fname
    else:
        fout = open(output, 'w')
    fout.write(f"""
    Analyse-Report Version 0.1
    Input: {fnames}
    \n{"-" * 60}\n""")
    if "combined" in result.keys():
        subheader = f"""
        {get_nested_val(result, ['combined', 'cat', 'sum', 'Z', 'SPACE', 'Zs', 'sum']):-{fpoint}} : ASCII Spacing Symbols
        {get_nested_val(result, ['combined', 'cat', 'sum', 'N', 'DIGIT', 'Nd', 'sum']):-{fpoint}} : ASCII Digits
        {get_nested_val(result, ['combined', 'cat', 'sum', 'L', 'LATIN', 'sum']):-{fpoint}} : ASCII Letters
        {get_nested_val(result, ['combined', 'cat', 'sum', 'L', 'LATIN', 'Ll', 'sum']):-{fpoint}} : ASCII Lowercase Letters
        {get_nested_val(result, ['combined', 'cat', 'sum', 'L', 'LATIN', 'Lu', 'sum']):-{fpoint}} : ASCII Uppercase Letters
        {get_nested_val(result, ['combined', 'cat', 'sum', 'P', 'sum']):-{fpoint}} : Punctuation & Symbols
        {get_nested_val(result, ['combined', 'cat', 'sum', 'sum']):-{fpoint}} : Total Glyphes
    """
        report_subsection(fout, "L", defaultdict(str), header="Statistics combined", subheaderinfo=subheader)
    if args.guidelines in result["guidelines"].keys():
        violations = sum_statistics(result["guidelines"], args.guidelines)
        report_subsection(fout, args.guidelines, result["guidelines"], \
                          header=f"{args.guidelines} Guidelines Evaluation",
                          subheaderinfo=f"Guideline violations combined: {violations}")
    for category in args.categorize:
        if category in result["combined"]["usr"].keys():
            occurences = sum_statistics(result["combined"]["usr"], category)
            report_subsection(fout, category, result["combined"]["usr"], \
                              header=f"Category statistics: {category}",
                              subheaderinfo=f"Overall occurrences: {occurences}")
    if "combined" in result.keys():
        if "all" in args.statistical_categories:
            result["combined"]["all"]["character"] = dict(result["combined"]["all"]["character"].most_common())
            report_subsection(fout, "all", result["combined"], header={"Overall unicode character statistics"})
        for cat in set(args.statistical_categories).intersection(set(result["combined"].keys())):
            if cat in ["all", "sum"]: continue
            report_subsection(fout, cat, result["combined"]["cat"], header={"L": "Overall Letter statistics",
                                                                            "Z": "Overall Separator statistics",
                                                                            "P": "Overall Punctuation statistics",
                                                                            "M": "Overall Mark statistics",
                                                                            "N": "Overall Number statistics",
                                                                            "S": "Overall Symbol statistics",
                                                                            "C": "Overall Other statistics"}.get(cat))
    fout.flush()
    if fout != sys.stdout:
        fout.close()
    return


def create_json(results: dict, output: Path) -> None:
    """
    Prints the results as json
    :param results: results instance
    :param output: output path
    :return:
    """
    if output:
        jout = output.with_suffix(".json").open("w", encoding='utf-8')
    else:
        jout = sys.stdout
    json.dump(results, jout, indent=4, ensure_ascii=False)
    jout.flush()
    jout.close()
    return


def set_output(args):
    """
    Sets the output format for the report, if output is None it prints to stdout
    :param output:
    :return:
    """
    output = args.output
    if not output: return
    if not output.parent.exists():
        output.parent.mkdir()
    if not output.is_file():
        output = output.joinpath("result.txt")
    args.output = output
    return


def main():
    """
    Reads text files, evaluate the unicode character and creates a report
    :return:
    """
    # Set filenames or path
    args.orig_fname = args.fname
    if len(args.fname) == 1 and not args.fname[0].is_file():
        args.fname = list(Path(args.fname[0]).rglob("*.gt.txt"))

    results = defaultdict(OrderedDict)

    # Read all files
    for fname in args.fname:
        with io.open(fname, 'r', encoding='utf-8') as fin:
            try:
                text = unicodedata.normalize(args.textnormalization, fin.read().strip())
                get_defaultdict(results['single'], fname)
                results['single'][fname]['text'] = text
            except UnicodeDecodeError:
                if args.verbose:
                    print(fname.name + " (ignored)")
                continue

    # Analyse the combined statistics
    get_defaultdict(results, 'combined')
    results['combined']['all']['character'] = Counter(
        "".join([text for fileinfo in results['single'].values() for text in fileinfo.values()]))
    # Categorize the combined statistics with standard categories
    categorize(results, category='combined')

    # Categorize the combined statistics with customized categories
    for category in args.categorize:
        categorize(results, category=category)

    # Validate the text against the guidelines
    validate_with_guidelines(results, args)

    # Summerize category data
    for section in ["cat", "usr"]:
        for key in set(results["combined"][section].keys()):
            summerize(results["combined"][section], key)

    # Result output
    set_output(args)
    create_report(results, args.output)
    if args.json: create_json(results, args.output)


if __name__ == '__main__':
    main()
