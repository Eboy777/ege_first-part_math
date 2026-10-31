from html.parser import HTMLParser
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from django.core.exceptions import ValidationError


MATH_TAGS={'math','semantics','mrow','mstyle','mi','mo','mn','mtext','msup','msub','msubsup','mfrac','msqrt','mroot','mover','munder','munderover','mtable','mtr','mtd','mfenced','mspace'}

class SourceHTMLValidator(HTMLParser):
    def __init__(self, image_paths):
        super().__init__(convert_charrefs=True)
        self.image_paths=image_paths
    def handle_starttag(self, tag, attrs):
        if tag not in {'p','div','span','i','b','strong','em','sup','sub','br','img'} | MATH_TAGS:
            raise ValidationError('Недопустимый тег условия.')
        values=dict(attrs)
        if tag=='img':
            if set(values)-{'src','alt','class'} or values.get('src') not in self.image_paths or values.get('class') not in {'formula','illustration'}:
                raise ValidationError('Недопустимое изображение в условии.')
        elif tag in MATH_TAGS:
            allowed={'xmlns':'http://www.w3.org/1998/Math/MathML','accent':{'true','false'},'displaystyle':{'true','false'},'stretchy':{'true','false'}}
            for key,value in attrs:
                choices=allowed.get(key)
                if choices is None or (isinstance(choices,set) and value not in choices) or (isinstance(choices,str) and value!=choices):
                    raise ValidationError('Недопустимый атрибут MathML.')
        elif attrs:
            raise ValidationError('Атрибуты условия не разрешены.')
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
    def handle_endtag(self,tag):
        if tag not in {'p','div','span','i','b','strong','em','sup','sub','br','img'} | MATH_TAGS:
            raise ValidationError('Недопустимый тег условия.')
    def handle_decl(self,decl):
        raise ValidationError('Декларации в условии запрещены.')


def verify_svg(path):
    data=Path(path).read_bytes()
    if len(data)>2_000_000 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Unsafe SVG')
    root=ET.fromstring(data)
    if root.tag.split('}')[-1]!='svg':raise ValueError('Not SVG')
    allowed={'svg','g','defs','path','use','symbol','clipPath','rect','line','polyline','polygon','circle','ellipse','text','tspan','title','desc'}
    for node in root.iter():
        if node.tag.split('}')[-1] not in allowed:raise ValueError('Unsafe SVG tag')
        for key,value in node.attrib.items():
            key=key.split('}')[-1]
            if key.lower().startswith('on') or (key=='href' and not value.startswith('#')):
                raise ValueError('Unsafe SVG attribute')
            if re.search(r'(?:https?:|javascript:|data:|//)',value,re.I):raise ValueError('External SVG reference')
            if 'url(' in value.lower() and not re.fullmatch(r'url\(#[\w.-]+\)',value):raise ValueError('External SVG reference')


def canonical_source_html(statement, root):
    """Ignore relocated URLs; include formula alt text and actual diagram bytes."""
    import hashlib
    import unicodedata
    chunks=[]
    class Reader(HTMLParser):
        def handle_data(self,data):chunks.append(data)
        def handle_starttag(self,tag,attrs):
            values=dict(attrs)
            if tag=='img':
                if values.get('class')=='formula':chunks.append(values.get('alt',''))
                else:
                    path=Path(root)/values['src'].removeprefix('/assets/tasks/')
                    chunks.append(hashlib.sha256(path.read_bytes()).hexdigest())
        def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs)
    Reader(convert_charrefs=True).feed(statement)
    return ' '.join(unicodedata.normalize('NFKC',' '.join(chunks)).replace('\xad','').split())
