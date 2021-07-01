from pathlib import Path
from collections import defaultdict, OrderedDict

from lib.io import open_stream_to
from lib.settings import load_settings


class Processhandler(object):

    def __init__(self, fpaths, output, guideline,guidelinespath, textnormalization, verbose):
        self.files = self._get_filenames(fpaths)
        self.current_file = None
        self.output = output
        self.guideline = guideline
        self.guidelines = load_settings(guidelinespath)
        self.textnormalization = textnormalization
        self.verbose = verbose

    def _get_filenames(self, fpaths):
        files = defaultdict(list)
        for fpath in fpaths:
            fpath = Path(fpath)
            if not fpath.is_file():
                for fname in sorted(fpath.rglob("*.gt.txt")):
                    files[fname.parent].append(fname)
            else:
                files[fpath.parent].append(fpath)
        return files

    def num_filenames(self):
        return len(self.files)

    def print(self, msg):
        if self.verbose:
            print(msg)


class Evaluatehandler(Processhandler):

    def __init__(self, fpaths, output,  json, custom_categories, statistical_categories,
             addinfo, guideline, textnormalization, log, verbose):
        self.fout = None
        self.orig_fname = None
        self.json = json
        self.statistical_categories = statistical_categories
        self.custom_categories = custom_categories
        self.addinfo = addinfo
        self.logging = None
        self.log = log
        super().__init__(fpaths, output, guideline, "settings/evaluate/guidelines", textnormalization, verbose)


class Revaluatehandler(Processhandler):
    def __init__(self, fpaths, output,
         lang, psm, diffratio, guideline,
         textnormalization, substitutiontext, delete_suspicous, log, verbose):
        self.filecounter = 0
        self.diffratio = diffratio
        self.difflogging = None
        self.lang = lang
        self.psm = psm
        self.logging = None
        self.delete_suspicous = delete_suspicous
        self.log = log
        self.substitutiontext = substitutiontext
        super().__init__(fpaths, output, guideline, "settings/revaluate/guidelines", textnormalization, verbose)

    def update_logger(self):
        if self.diffratio:
            self.difflogging = open_stream_to(self.difflogging, Path(self.current_file.joinpath(f"diffratio_{int(self.diffratio * 100)}.log")))
        if self.log:
            self.logging = open_stream_to(self.logging, Path(self.current_file.joinpath("substitution.log")))

    def close_logger(self):
        # close stream to log files
        for logger in [self.difflogging, self.logging]:
            logger.close()

    def write_log(self, logging, msg):
        if logging:
            logging.write(msg)
            logging.flush()

