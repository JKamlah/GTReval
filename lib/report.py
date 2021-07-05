import unicodedata
from typing import DefaultDict
from collections import defaultdict
import sys

from lib.functools import get_defaultdict
from lib.evaluation import controlcharacter_check

def print_unicodeinfo(eval, val, key) -> str:
    """
    Prints the occurrence, unicode character or guideline rules and additional information
    :param eval: arguments instance
    :param val: count of the occurrences of key
    :param key: key (glyph or guideline rules)
    :return:
    """
    # The \u200E is the LR Mark so the text is rendered from left to right even if the next symbol is RL
    if isinstance(val, int):
        return f"\u200E{val:-{6}}  {'{'}{repr(key) if controlcharacter_check(key) else key}{'}'}{addinfo(eval, key)}"
    elif isinstance(val, str) and len(unicodedata.normalize('NFD', val)) == 2:
        val = unicodedata.normalize('NFD', val)
        return f"\u200E{'{'}{repr(key) if controlcharacter_check(key) else key}{'}'} " \
               f"U+{str(hex((ord(val[0])))).replace('0x', '').zfill(4)}-U+{str(hex((ord(val[1])))).replace('0x', '').zfill(4)} " \
               f"{addinfo(eval, val)}"
    else:
        return f"\u200E{'{'}{repr(key) if controlcharacter_check(key) else key}{'}'} U+{str(val).replace('0x','').zfill(4)} {int(val, 16)}{addinfo(eval, key)}"


def addinfo(eval, key) -> str:
    """
    Adds info to the single unicode statistics like the hexa code or the unicodename
    :param eval: arguments instance
    :param key: key string (glyphs or guideline rules)
    :return:
    """
    info = " "
    if len(key) > 1:
        if len(key)==2:
            if "code" in eval.addinfo:
                try:
                    info += f"{str(hex(ord(key[0])))} - {str(hex(ord(key[1])))} "
                except ValueError:
                    info += f"NO NAME IS AVAILABLE FOR {key}"
            if "name" in eval.addinfo:
                try:
                    info += f"{unicodedata.name(key[0])} - {unicodedata.name(key[1])}"
                except ValueError:
                    info += f"NO NAME IS AVAILABLE FOR {key}"
        elif controlcharacter_check(key):
            return info+"CONTROL CHARACTER"
    else:
        if "code" in eval.addinfo:
            info += str(hex(ord(key))) + " "
        if "name" in eval.addinfo:
            try:
                info += unicodedata.name(key)
            except ValueError:
                info += f"NO NAME IS AVAILABLE FOR {str(hex(ord(key)))}"
    return info.rstrip()


def report_subsection(fout, subsection: str, result: DefaultDict, eval, header="", subheaderinfo="") -> None:
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
        if isinstance(conditionres, list):
            if not conditionres: continue
            for subval in sorted(conditionres):
                if isinstance(subval, int):
                    fout.write(f"""
                         {print_unicodeinfo(eval, str(hex(subval)), chr(subval))}""")
                else:
                    fout.write(f"""
                         {print_unicodeinfo(eval, subval, subval)}""")
        else:
            for key, val in conditionres.items():
                if isinstance(val, list):
                    if not val: continue
                    for subval in sorted(val):
                        fout.write(f"""
                             {print_unicodeinfo(eval, str(hex(subval)), chr(subval))}""")
                elif isinstance(val, dict):
                    fout.write(f"""
                {key}:""")
                    for subkey, subval in sorted(val.items()):
                        if isinstance(subkey, int) or len(subkey) == 1:
                            subkey = ord(subkey)
                            fout.write(f"""
                                {print_unicodeinfo(eval, subval, subkey)}""")
                        else:
                            fout.write(f"""
                                {print_unicodeinfo(eval, subval, chr(subkey))}""")
                else:
                    if isinstance(key, int):
                        fout.write(f"""
                            {print_unicodeinfo(eval, val, chr(key))}""")
                    else:
                        fout.write(f"""
                            {print_unicodeinfo(eval, val, key)}""")
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


def summarize(results: DefaultDict, category: str) -> None:
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


def create_report(result: DefaultDict, eval) -> None:
    """
    Creates the report
    :param result: results instance
    :param eval: evaluation processhandler
    :return:
    """
    fpoint = 10
    fnames = "; ".join(set([str(fpath.resolve()) for fpath in eval.files.keys()]))
    if not eval.output:
        eval.fout = sys.stdout
    else:
        eval.fout = open(eval.output, 'w')
    eval.fout.write(f"""
    Analyse-Report Version 0.1
    Input: {fnames}
    \n{"-" * 60}\n""")
    if "combined" in result.keys():
        subheader = f"""
        {get_nested_val(result, ['combined', 'cat', 'sum', 'Z', 'SPACE', 'Zs', 'sum']):-{fpoint}} ASCII Spacing Symbols
        {get_nested_val(result, ['combined', 'cat', 'sum', 'N', 'DIGIT', 'Nd', 'sum']):-{fpoint}} ASCII Digits
        {get_nested_val(result, ['combined', 'cat', 'sum', 'L', 'LATIN', 'sum']):-{fpoint}} ASCII Letters
        {get_nested_val(result, ['combined', 'cat', 'sum', 'L', 'LATIN', 'Ll', 'sum']):-{fpoint}} ASCII Lowercase Letters
        {get_nested_val(result, ['combined', 'cat', 'sum', 'L', 'LATIN', 'Lu', 'sum']):-{fpoint}} ASCII Uppercase Letters
        {get_nested_val(result, ['combined', 'cat', 'sum', 'P', 'sum']):-{fpoint}} Punctuation & Symbols
        {get_nested_val(result, ['combined', 'cat', 'sum', 'sum']):-{fpoint}} Total Glyphs
    """
        report_subsection(eval.fout, "L", defaultdict(str), eval, header="Statistics combined", subheaderinfo=subheader)
    if eval.guideline in result["guidelines"].keys():
        violations = sum_statistics(result["guidelines"], eval.guideline)
        report_subsection(eval.fout, eval.guideline, result["guidelines"],eval,
                          header=f"{eval.guideline} Guidelines Evaluation",
                          subheaderinfo=f"Guideline violations combined: {violations}")
    for category in eval.custom_categories:
        if category in result["combined"]["usr"].keys():
            occurences = sum_statistics(result["combined"]["usr"], category)
            report_subsection(eval.fout, category, result["combined"]["usr"],eval,
                              header=f"Category statistics: {category}",
                              subheaderinfo=f"Overall occurrences: {occurences}")
    if "combined" in result.keys():
        if "all" in eval.statistical_categories:
            result["combined"]["all"]["Glyph"] = dict(result["combined"]["all"]["Glyph"].most_common())
            report_subsection(eval.fout, "all", result["combined"], eval, header="Unicode glyph statistics")
        for cat in set(eval.statistical_categories).intersection(set(result["combined"].keys())):
            if cat in ["all", "sum"]: continue
            report_subsection(eval.fout, cat, result["combined"]["cat"], eval,header={"L": "Letter statistics",
                                                                            "Z": "Separator statistics",
                                                                            "P": "Punctuation statistics",
                                                                            "M": "Mark statistics",
                                                                            "N": "Number statistics",
                                                                            "S": "Symbol statistics",
                                                                            "C": "Other statistics"}.get(cat))
        if "missing" in result["combined"].keys():
            for cat in result["combined"]["missing"].keys():
                report_subsection(eval.fout, cat, result["combined"]['missing'], eval,header=f"Missing characters for profile '{cat}'")

    eval.fout.flush()
    if eval.fout != sys.stdout:
        eval.fout.close()
    return