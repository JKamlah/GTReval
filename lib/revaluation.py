from pathlib import Path
import unicodedata
import difflib
import re
import imghdr

from lib.editing import update_replacement, string_index_replacement, substitutiontext

from tesserocr import PyTessBaseAPI


def revaluate_ocr(gt: str, filename: Path, reval):
    """
    Reads the guideline, ocr the image, compares the original groundtruth text and the ocr'd text and substitutes if it
    is indicated by the guidelines.
    :param gt: groundtruth text
    :param filename: gt filename
    :param args: arguments instance
    :return:
    """
    try:
        imgname = [img for img in filename.parent.rglob(f"{filename.name.split('gt.txt')[0]}*[!.txt]") if imghdr.what(img)][0]
    except StopIteration:
        print(f"No picture found for {filename}")
        reval.write_log(reval.logging, f"No picture found for {filename}")
        return gt
    with PyTessBaseAPI(psm=reval.psm, lang=reval.lang) as api:
        api.SetImageFile(str(imgname))
        ocr = unicodedata.normalize(reval.textnormalization, api.GetUTF8Text()).strip()
    gtlist = list(gt)
    if reval.guidelines and reval.guideline in reval.guidelines.keys():
        for conditionkey, conditions in reval.guidelines[reval.guideline].items():
            s = difflib.SequenceMatcher(None, gt, ocr)
            if s.ratio() > 0.3:
                subtext = f"{filename.name}: "
                for groupname, *value in s.get_opcodes():
                    gtsubstring = gt[value[0]:value[1]]
                    if groupname == "replace":
                        if "unicode" in conditionkey.lower():
                            foundidx = 0
                            for gtidx, ocridx in zip(range(value[0], value[1]), range(value[2], value[3])):
                                glyphs = reval.guidelines[reval.guideline][conditionkey].get(gt[gtidx], [])
                                for glyph in glyphs:
                                    if ocr[ocridx] == "\n": continue
                                    if ord(ocr[ocridx]) == glyph or str(glyph) in unicodedata.name(
                                            str(ocr[ocridx])):
                                        ocr = update_replacement(reval.guidelines[reval.guideline][conditionkey], gt[gtidx], ocr, ocridx)
                                        gtlist[gtidx] = ocr[ocridx]
                                        if reval.verbose or reval.log:
                                            gtsubstring = string_index_replacement(gtsubstring, gtidx-value[0], substitutiontext(gt[gtidx], ocr[ocridx]))
                                        foundidx = ocridx
                                        break
                            if (value[1] - value[0]) - (value[3] - value[2]) != 0:
                                for gtidx, ocridx in zip(range(value[1], value[0]), range(value[3], value[2])):
                                    if ocridx <= foundidx: break
                                    glyphs = reval.guidelines[reval.guideline][conditionkey].get(gt[gtidx], [])
                                    for glyph in glyphs:
                                        if ocr[ocridx] == "\n": continue
                                        if ord(ocr[ocridx]) == glyph or str(glyph) in unicodedata.name(
                                                str(ocr[ocridx])):
                                            ocr = update_replacement(reval.guidelines[reval.guideline][conditionkey], gt[gtidx],
                                                                     ocr, ocridx)
                                            gtlist[gtidx] = ocr[ocridx]
                                            if reval.verbose or reval.log:
                                                gtsubstring = string_index_replacement(gtsubstring, gtidx - value[0],
                                                                                       substitutiontext(gt[gtidx],
                                                                                                        ocr[ocridx]))
                                            break
                        else:
                            for glkey in reval.guidelines[reval.guideline][conditionkey].keys():
                                for gtmatch in re.finditer(glkey, gt[value[0]:value[1]]):
                                    for ocrreg in reval.guidelines[reval.guideline][conditionkey][glkey]:
                                        ocrmatch = re.search(ocrreg,ocr[value[2] + gtmatch.start():])
                                        if ocrmatch and ocrmatch.start() == 0:
                                            ocr = update_replacement(reval.guidelines[reval.guideline][conditionkey], glkey, ocrmatch[0], 0)
                                            if reval.verbose or reval.log:
                                                gtsubstring = string_index_replacement(gtsubstring, gtmatch.start(), substitutiontext(gtsubstring[gtmatch.start():gtmatch.end()], ocrmatch[0]), gtmatch.start()+gtmatch.end())
                                            gtlist[value[0]+gtmatch.start()] = ocrmatch[0]
                                            gtlist[value[0]+gtmatch.start()+1:value[0]+gtmatch.end()] = ""
                                            break

                    subtext += gtsubstring

                if gt.strip() != subtext.split(":", 1)[1].strip():
                    reval.print(subtext)
                    reval.write_log(reval.logging, subtext + '\n')
            gt = "".join(gtlist)
    if s.ratio() < reval.diffratio:
        if reval.delete_suspicous and len(gt) > 5:
            if s.ratio() < reval.diffratio:
                reval.filecounter+=1
                print(f"{reval.filencounter}/{reval.num_filenames} - {s.ratio()}%")
                import os
                os.remove(str(filename))
                os.remove(str(filename).replace(".gt.txt",".png"))
        else:
            if s.ratio() < reval.diffratio:
                reval.write_log(reval.difflogging, f"Ratio:{s.ratio():.3f} Filename:{filename.name}\n"
                                   f"{'*'*50}\n"
                                   f"GT:  {gt}\n"
                                   f"OCR: {ocr}\n"
                                   f"DIFF:")
                for groupname, *value in s.get_opcodes():
                    reval.write_log(reval.difflogging,{'equal': gt[value[0]:value[1]],
                                        'replace': f"--{gt[value[0]:value[1]]}--++{ocr[value[2]:value[3]]}++",
                                        'insert': f"++{ocr[value[2]:value[3]]}++",
                                        'delete': f"--{gt[value[0]:value[1]]}--"}.get(groupname, ""))
                reval.write_log(reval.difflogging,'\n\n')
    return "".join(gtlist)