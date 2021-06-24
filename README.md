GTReval
--------
![Python 3.6](https://img.shields.io/badge/python-3.6-yellow.svg)
![license](https://img.shields.io/badge/license-Apache%20License%202.0-blue.svg)

## Overview
**Evaluates and Revaluates Ground Truth data**

Evaluates the data based on OCR-D guideline rules or user created rules.  
Revaluates the data based on a tesseract model and a guideline rules or user created rules. 

## Installation
This installation is tested with Ubuntu and we expect that it should
work for other similar environments.

### 1. Requirements
- Python >= 3.6
- tesserocr

### 2. Copy this repository
```
git clone https://github.com/JKamlah/GTReval.git
cd GTReval
```

### 3. Installation into a Python Virtual Environment

    $ python3 -m venv venv
    $ source venv/bin/activate
    $ pip install -r requirements.txt

## Process steps

### Start the process

    $ python3 evaluate.py path/to/gt args
    $ python3 revaluate.py path/to/gt args

### Settings file
The settings file contain OCR-D guideline rules, but it can also get extended by the user.
The profile is set by [profilename]. 
'==' separates the type of the rules, e.g. unicode, and the arguments.
'||' separates multiple arguments.

#### Evaluate
The type of rules can be set either by Unicode violaten or Regex violation.
Unicode violation can contain either parts of the Unicode name or the unicode character.
Regex violation can contain regex expression.

```
[Example]  
Unicode violation == LETTER LONG S  
Regex violation == ꝛc\.||\s\s||[A-z]\s[,;\.]
```

#### Revaluate
The type of rules can be set either by Unicode or Regex.  
Unicode can contain either parts of the Unicode name or the unicode character.  
Regex can contain regex expression.  
'-->' indicates which gt char should be replace with. B (gt) --> D (ocr)  
'<-->' indicates which gt char can be replaced with, but also reversed.  
 B (gt) <--> D (ocr) leads to  B (gt) --> D (ocr) and D (gt) --> B (ocr)
```
[Example]  
Unicode ==  B <--> V  
            ¬ --> = || ¬ || ₌ || —  
Regex == ß --> sz 
``` 
 
Copyright and License
--------

Copyright (c) 2020 Universitätsbibliothek Mannheim

Author:
 * [Jan Kamlah](https://github.com/jkamlah)

**GTReval** is Free Software. You may use it under the terms of the Apache 2.0 License.
See [LICENSE](./LICENSE) for details.
