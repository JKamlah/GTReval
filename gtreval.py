#!/usr/bin/env python3
import io
import unicodedata
from collections import defaultdict, OrderedDict, Counter

import click
from tqdm import tqdm

from lib.editing import substitutiontext
from lib.evaluation import validate_with_guidelines, categorize, missing_unicode
from lib.functools import get_defaultdict
from lib.io import create_json, set_output, write_subcounter
from lib.processhandler import Revaluatehandler, Evaluatehandler
from lib.report import summarize, create_report
from lib.revaluation import revaluate_ocr
from lib.unicodetools import load_ucd


@click.group()
def cli():
    pass


# Command line arguments.
@cli.command()
@click.argument('fpaths', nargs=-1, type=click.Path(exists=True))
@click.option('-o', '--output', type=click.Path(), help='filename of the output report, \
                        if none is given the result is printed to stdout')
@click.option('-j', '--json', default=False, is_flag=True,
              help='will also output the all results as json file (including the guideline_violations)')
@click.option('-c', '--custom_categories', help='Customized unicodedata categories',
              default=[''], multiple=True)
@click.option('-s', '--statistical-categories',
              help='Customized unicodedata categories. "all" prints information about '
                   'all unicode glyphs ordered by occurence. The other options ar "L" for Letter, '
                   '"Z" for Separator, "P" for Punctuation, "M" for Mark,'
                   '"N" for Number, "S" for Symbol,i "C" for Other',
              default=['all'], type=click.Choice(['L', 'M', 'N', 'P', 'S', 'Z', 'C', 'all']), multiple=True)
@click.option('-m', '--missing-unicodes',
              help="Print missing unicodes in the dataset by either a profile from profiles/evaluate/missing_unicode, "
                   "a unicode rang e.g. , '0x0000-0x007F, 0x0100-0x017F'",
              type=click.STRING, multiple=True)
@click.option('-a', '--addinfo', help="Add information, such as unicode name and/or code to output",
              default=['name'], type=click.Choice(['name', 'code']), multiple=True)
@click.option('-g', '--guideline', help="Guidelines for the automatic revaluation",
              type=click.Choice(['OCR-D-1', 'OCR-D-2', 'OCR-D-3', 'CUSTOM']))
@click.option('-t', '--textnormalization', help="Unicode text normalization", default='NFC',
              type=click.Choice(['NFC', 'NFKC', 'NFD', 'NFKD']))
@click.option('-l', '--log', default=False, is_flag=True, help='Logs process information')
@click.option('-v', '--verbose', default=False, is_flag=True, help='Print more process information')
def evaluate(fpaths, output, json, custom_categories, statistical_categories, missing_unicodes,
             addinfo, guideline, textnormalization, log, verbose):
    """
    Reads text files, evaluate the unicode character and creates a report
    :return:
    """
    evalu = Evaluatehandler(fpaths, output, json, custom_categories, statistical_categories,
                            addinfo, guideline, textnormalization, log, verbose)

    results = defaultdict(OrderedDict)

    # Read all files
    for fpath, fnames in evalu.files.items():
        for fname in fnames:
            evalu.orig_fname = fname
            with io.open(str(fname.resolve()), 'r', encoding='utf-8') as fin:
                try:
                    text = unicodedata.normalize(evalu.textnormalization, fin.read().strip())
                    get_defaultdict(results['single'], fname)
                    results['single'][fname]['text'] = text
                except UnicodeDecodeError:
                    if evalu.verbose:
                        print(f"{fname.name} (ignored)")
                    continue

    # Analyse the combined statistics
    get_defaultdict(results, 'combined')
    res_all = results['combined']['all']
    res_all['glyph'] = Counter(
        ''.join([text for fileinfo in list(results['single'].values()) for text in fileinfo.values()]))
    res_all['combined glyph'] = Counter(
        [text[idx - 1] + char for fileinfo in list(results['single'].values()) for text in fileinfo.values()
         for idx, char in enumerate(text) if ord(char) in [*list(range(768, 879 + 1)),
                                                           *list(range(6832, 6848 + 1)),
                                                           *list(range(7616, 7664 + 1)),
                                                           *list(range(8400, 8432 + 1)),
                                                           *list(range(65056, 65071 + 1))] and idx != 0])
    res_all['codepoints'] = {ord(glyph): val for glyph, val in
                                                results['combined']['all']['glyph'].items()}
    # Categorize the combined statistics with standard categories
    categorize(results, category='combined')

    # Categorize the combined statistics with customized categories
    for category in evalu.custom_categories:
        categorize(results, category=category)

    # Find missing unicode glyphs
    if missing_unicodes:
        ucd = load_ucd(update=True)
        for missing_unicode_profile in missing_unicodes:
            missing_unicode(results, evalu, ucd, profile=missing_unicode_profile)

    # Validate the text against the guidelines
    if guideline:
        validate_with_guidelines(results, evalu)

    # Summarize category data
    for section in ['cat', 'usr']:
        if section in results['combined'].keys():
            for key in set(results['combined'][section].keys()):
                summarize(results['combined'][section], key)

    # Don't need codepoints information anymore TODO: Rework this!
    del res_all['codepoints']

    # Result output
    set_output(evalu)
    create_report(results, evalu)
    if evalu.json:
        create_json(results, evalu.output)
    return


@cli.command()
@click.argument('fpaths', nargs=-1, type=click.Path(exists=True))
@click.option('-o', '--output', type=click.Path(), help='filename of the output report, \
                        if none is given the result is printed to stdout')
@click.option('--dry-run', default=False, is_flag=True, help="Don't store the ground truth text changes")
@click.option('-l', '--lang', default='eng', help='Tesseract language model')
@click.option('--psm', default=13, type=click.IntRange(0, 14), help='Tesseract pagesegementation mode')
@click.option('-d', '--diffratio', help='logs all ratios which are beyond the given ratio (0-1)', type=click.FLOAT,
              default=0)
@click.option('-g', '--guideline', help='Guidelines for the automatic revaluation', type=click.STRING,
              default='GT4HIST')
@click.option('-t', '--textnormalization', help='Unicode text normalization', default='NFC',
              type=click.Choice(['NFC', 'NFKC', 'NFD', 'NFKD']))
@click.option('--delete-suspicous', default=False, is_flag=True,
              help='Delete files which are lower than the diffratio with at least five characters')
@click.option('-l', '--log', default=False, is_flag=True, help='Logs process information')
@click.option('-v', '--verbose', default=False, is_flag=True, help='Print more process information')
def revaluate(fpaths, output, dry_run,
              lang, psm, diffratio, guideline,
              textnormalization, delete_suspicous, log, verbose):
    """
    Revaluate the ground truth texts for the given text files.
    """
    reval = Revaluatehandler(fpaths, output, lang, psm,
                             diffratio, guideline, textnormalization,
                             substitutiontext, delete_suspicous, log, verbose)
    # read all files
    for filepath, filenames in tqdm(reval.files.items()):
        reval.filecounter = 0
        # open stream to log files
        reval.substitutiontext.calls = defaultdict(int)

        for filename in tqdm(filenames):
            reval.current_file = filename
            reval.update_logger()
            try:
                gt = unicodedata.normalize(textnormalization, filename.read_text().lstrip())
                # Revaluate gt with ocr results
                revaluated_gt = revaluate_ocr(gt, filename, reval)

                if revaluated_gt != gt and not dry_run:
                    filename.open('w').write(revaluated_gt)

            except UnicodeDecodeError:
                reval.print(f"{filename.name} (ignored)")
                continue

        # Print counter
        write_subcounter(reval)


if __name__ == '__main__':
    cli()
