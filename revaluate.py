#!/usr/bin/env python3

import argparse
import difflib
import re
import unicodedata
from collections import defaultdict, OrderedDict
from functools import lru_cache
from pathlib import Path

from tesserocr import PyTessBaseAPI

# Command line arguments.
arg_parser = argparse.ArgumentParser(description='Revaluate the ground truth texts for the given text files.')
arg_parser.add_argument("filename", type=lambda x: Path(x), help="filename of text file or path to files", nargs='*')
arg_parser.add_argument("-o", "--output", type=lambda x: Path(x) if x is not None else None, default=None,
                        help="filename of the output report, \
                        if none is given the result is printed to stdout")
arg_parser.add_argument("--dry-run", help="Don't store the ground truth text changes", action="store_true")
arg_parser.add_argument("-m", "--model", default="Fast_GT4HIST/Fraktur_50000000.502_198857",
                        help="Tesseract model to perform the ocr")  # Fast_ONB/FrakturONB1.939_155730  Fast_GT4HIST/Fraktur_50000000.502_198857
arg_parser.add_argument("--psm", default=13, type=int, choices=range(0, 14), help="Tesseract pagesegementation mode")
arg_parser.add_argument("-d", "--diffratio", help="logs all ratios which are beyond the given ratio (0-1)", type=float,
                        default=0.9)
arg_parser.add_argument("-r", "--revaluate", help="Guidelines for the automatic revaluation", type=str,
                        default="GT4HIST")
arg_parser.add_argument("-t", "--textnormalization", help="Textnormalization settings", type=str, default="NFC",
                        choices=["NFC", "NFKC", "NFD", "NFKD"])
arg_parser.add_argument("-l", "--log", help="logs glyphe subsitutions", action="store_true")
arg_parser.add_argument("-v", "--verbose", help="shows information, like glyphe subsitutions", action="store_true")


def get_defaultdict(resultslvl, newlvl, instance=OrderedDict):
    resultslvl[newlvl] = defaultdict(instance) if not resultslvl.get(newlvl, None) else resultslvl[newlvl]

@lru_cache()
def load_settings(filename: str):
    settings = defaultdict(dict)
    setting, subsetting = None, None
    with open(Path(filename), 'r') as fin:
        for line in fin.readlines():
            line = line.strip()
            if len(line) < 1 or line[0] == '#': continue
            if line[0] + line[-1] == '[]':
                setting = line.strip('[]')
                get_defaultdict(settings, setting, instance=dict)
                continue
            if setting:
                if '==' in line:
                    subsetting, line = [part.strip() for part in line.split("==")]
                    get_defaultdict(settings[setting], subsetting, instance=list)
                if subsetting and isinstance(settings[setting][subsetting], dict):
                    lines = [line]
                    if '<-->' in line:
                        parts = line.split('<-->')
                        lines = [parts[0]+'-->'+parts[1], parts[1]+'-->'+parts[0]]
                    for line in lines:
                        orig, subs = [part.strip() for part in line.split('-->')]
                        for sub in subs.split('||'):
                            if '<--' in sub:
                                sub, rep = sub.split('<--')[:2]
                                settings[setting][subsetting]["<--"] = {orig: rep.strip()}
                            sub = sub.strip()
                            if '-' in sub and len(sub) > 1 and len(sub.split('-')) == 2:
                                settings[setting][subsetting][orig].append(range(
                                    *sorted([int(val) if not '0x' in val else int(val, 16) for val in sub.split('-')])))
                            else:
                                if len(sub) == 1:
                                    settings[setting][subsetting][orig].append(ord(sub))
                                if sub.isdigit():
                                    settings[setting][subsetting][orig].append(int(sub))
                                elif sub[:2] == '0x':
                                    settings[setting][subsetting][orig].append(int(sub, 16))
                                else:
                                    settings[setting][subsetting][orig].append(sub)

        if setting and subsetting:
            return settings


def next_ocrmatch(subs, ocr):
    for sub in subs:
        for ocrmatch in re.finditer(sub, ocr):
            yield ocrmatch

def subcounter(func):
    def helper(*_args, **_kwargs):
        helper.calls[_args[0]+"→"+_args[1]] += 1
        return func(*_args, **_kwargs)
    helper.calls = defaultdict(int)
    return helper


@subcounter
@lru_cache()
def substitutiontext(gtmatch, ocrmatch):
    return f"--{gtmatch}--++{ocrmatch}++"

def update_replacement(guideline, gt, ocr, ocridx):
    rep = guideline.get("<--").get(gt, None) if guideline.get('<--',None) else None
    if rep:
        if isinstance(ocr, str):
            ocrlist = list(ocr)
            ocrlist[ocridx] = rep
            ocr = "".join(ocrlist)
        else:
            ocr[ocridx] = rep
    return ocr


def revaluate(gt: str, filename: Path, args):
    guideline = args.revaluate
    guidelines = load_settings("settings/revaluate/guidelines")
    try:
        imgname = next(filename.parent.rglob(f"{filename.name.split('gt.txt')[0]}*[!.txt]"))
    except StopIteration:
        print(f"No picture found for {filename}")
        args.log.write(f"No picture found for {filename}")
        return gt
    # file_to_text seems to produce sometimes false results
    #ocr = unicodedata.normalize(args.textnormalization, file_to_text(str(imgname), lang=args.model, psm=args.psm)).strip()
    with PyTessBaseAPI(psm=args.psm, lang=args.model) as api:
        api.SetImageFile(str(imgname))
        ocr = unicodedata.normalize(args.textnormalization, api.GetUTF8Text()).strip()
    gtlist = list(gt)
    if guidelines and guideline in guidelines.keys():
        for conditionkey, conditions in guidelines[guideline].items():
            s = difflib.SequenceMatcher(None, gt, ocr)
            if s.ratio() > 0.3:
                subtext = f"{filename.name}: "
                for groupname, *value in s.get_opcodes():
                    gtsubstring = gt[value[0]:value[1]]
                    if groupname == "replace":
                        if "unicode" in conditionkey.lower():
                            for gtidx, ocridx in zip(range(value[0], value[1]), range(value[2], value[3])):
                                if gt[gtidx] in guidelines[guideline][conditionkey].keys():
                                    for glyphe in guidelines[guideline][conditionkey][gt[gtidx]]:
                                        if ocr[ocridx] == "\n": continue
                                        if ord(ocr[ocridx]) == glyphe or str(glyphe) in unicodedata.name(
                                                str(ocr[ocridx])):
                                            ocr = update_replacement(guidelines[guideline][conditionkey], gt[gtidx], ocr, ocridx)
                                            gtlist[gtidx] = ocr[ocridx]
                                            if args.verbose or args.log:
                                                gtsubstring = substitutiontext(gt[gtidx], ocr[ocridx])
                                            break

                        else:
                            for glkey in guidelines[guideline][conditionkey].keys():
                                for gtmatch in re.finditer(glkey, gt[value[0]:value[1]]):
                                    for ocrmatch in next_ocrmatch(guidelines[guideline][conditionkey][glkey],
                                                                  ocr[value[2] + gtmatch.start()]):
                                        if ocrmatch.start() == 0:
                                            ocr = update_replacement(guidelines[guideline][conditionkey], glkey, ocrmatch, 0)
                                            if args.verbose or args.log:
                                                gtsubstring = substitutiontext(gtmatch[0], ocrmatch[0])
                                            gtlist[value[0]+gtmatch.start()] = ocrmatch[0]
                                            gtlist[value[0]+gtmatch.start()+1:value[0]+gtmatch.end()] = ""
                                        break

                    subtext += gtsubstring

                if gt != subtext.split(":", 1)[1].strip():
                    if args.verbose:
                        print(subtext)
                    if args.log:
                        args.log.write(subtext + '\n')
                        args.log.flush()

            gt = "".join(gtlist)

            if s.ratio() < args.diffratio and args.difflog:
                s = difflib.SequenceMatcher(None, gt, ocr)
                if s.ratio() < args.diffratio:
                    args.difflog.write(f"Ratio:{s.ratio():.3f} Filename:{filename.name}\n"
                                       f"{'*'*50}\n"
                                       f"GT:  {gt}\n"
                                       f"OCR: {ocr}\n"
                                       f"DIFF:")
                    for groupname, *value in s.get_opcodes():
                        args.difflog.write({'equal': gt[value[0]:value[1]],
                                            'replace': f"--{gt[value[0]:value[1]]}--++{ocr[value[2]:value[3]]}++",
                                            'insert': f"++{ocr[value[2]:value[3]]}++",
                                            'delete': f"--{gt[value[0]:value[1]]}--"}.get(groupname, ""))
                    args.difflog.write('\n\n')
                    args.difflog.flush()
    return "".join(gtlist)


def open_stream_to(writer, fname):
    if isinstance(writer, Path):
        writer.close()
    if fname.exists():
        fname.unlink()
    fname.touch()
    return fname.open("r+")

def write_subcounter(args):
    subcountertxt = f"{'*' * 22}\nSubstitutions: " + \
                    "".join([f"\n\t{count:-{6}}: [{subs}]" for subs, count in substitutiontext.calls.items()]) + \
                    f"\n{'*' * 22}\n"
    if args.verbose:
        print(subcountertxt)
    if args.log:
        args.log.seek(0, 0)
        content = args.log.read()
        args.log.seek(0, 0)
        args.log.write(subcountertxt+content)
        args.log.flush()

def revaluate_directories(fileinfo, args):
    print(fileinfo)
    filepath, filenames = fileinfo
    # open stream to log files
    if args.diffratio:
        args.difflog = open_stream_to(args.difflog, Path(filepath.joinpath(f"diffratio_{int(args.diffratio * 100)}.log")))
    if args.log:
        args.log = open_stream_to(args.log, Path(filepath.joinpath("substitution.log")))
    for filename in sorted(filenames):
        try:
            gt = unicodedata.normalize(args.textnormalization, filename.read_text().strip())
            # Revaluate gt with ocr results
            revaluated_gt = revaluate(gt, filename, args)
            if revaluated_gt != gt and not args.dry_run:
                filename.open("w").write(revaluated_gt)

        except UnicodeDecodeError:
            if args.verbose:
                print(filename.name + " (ignored)")
            continue

    # Print counter
    if args.verbose or args.log:
        write_subcounter(args)

    # close stream to log files
    if args.diffratio:
        args.difflog.close()
    if args.log:
        args.log.close()

def main(args):
    # set filenames or path
    filenames = defaultdict(list)

    for filedir in args.filename:
        filepaths = args.filename
        if not args.filename[0].is_file():
            filepaths = Path(filedir).rglob("*.gt.txt")
        for filename in sorted(filepaths):
            filenames[filename.parent].append(filename)
    args.difflog = False
    # read all files
    for filepath, filenames in filenames.items():
        # open stream to log files
        substitutiontext.calls = defaultdict(int)
        if args.diffratio:
            args.difflog = open_stream_to(args.difflog, Path(filepath.joinpath(f"diffratio_{int(args.diffratio * 100)}.log")))
        if args.log:
            args.log = open_stream_to(args.log, Path(filepath.joinpath("substitution.log")))
        for filename in filenames:
            try:
                gt = unicodedata.normalize(args.textnormalization, filename.read_text().lstrip())
                # Revaluate gt with ocr results
                revaluated_gt = revaluate(gt, filename, args)
                if revaluated_gt != gt and not args.dry_run:
                    filename.open("w").write(revaluated_gt)

            except UnicodeDecodeError:
                if args.verbose:
                    print(filename.name + " (ignored)")
                continue

        # Print counter
        if args.verbose or args.log:
            write_subcounter(args)

        # close stream to log files
        if args.diffratio:
            args.difflog.close()
        if args.log:
            args.log.close()

if __name__ == '__main__':
    main(arg_parser.parse_args())
