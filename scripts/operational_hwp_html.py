"""Static, isolated presentation of parser-authored HWP review HTML."""
from html import escape
from html.parser import HTMLParser
import re

HTML_CSP = "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; base-uri 'none'; form-action 'none'"
TAGS = set('html head body title style div span p br hr table thead tbody tfoot tr th td colgroup col img h1 h2 h3 h4 h5 h6 strong b em i u s sub sup ul ol li section article header footer main aside blockquote pre code a mark'.split())
VOID = {'br', 'hr', 'col', 'img'}
BLOCKED = {'script', 'iframe', 'object', 'embed', 'svg', 'math', 'form', 'textarea', 'button', 'select', 'template'}
ATTRS = {'class', 'id', 'style', 'title', 'colspan', 'rowspan', 'width', 'height', 'alt', 'lang', 'dir'}


class StaticHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.blocked = []
        self.style_depth = 0

    def handle_starttag(self, tag, attrs):
        if self.blocked or tag in BLOCKED:
            self.blocked.append(tag)
            return
        if tag not in TAGS:
            return
        safe = []
        for key, value in attrs:
            if value is None:
                continue
            if key in ATTRS or re.fullmatch(r'data-[a-z0-9-]+', key):
                safe.append((key, value))
            elif tag == 'img' and key == 'src' and re.match(r'^data:image/(?:png|jpeg|gif|webp);base64,', value, re.I):
                safe.append((key, value))
        self.parts.append('<' + tag + ''.join(f' {key}="{escape(value, quote=True)}"' for key, value in safe) + '>')
        if tag == 'style':
            self.style_depth += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.blocked:
            if tag in self.blocked:
                # A malformed input can only omit content, never re-enable scripts.
                while self.blocked:
                    current = self.blocked.pop()
                    if current == tag:
                        break
            return
        if tag in TAGS and tag not in VOID:
            self.parts.append(f'</{tag}>')
        if tag == 'style':
            self.style_depth = max(0, self.style_depth - 1)

    def handle_data(self, data):
        if not self.blocked:
            self.parts.append(data if self.style_depth else escape(data))


def static_hwp_html(source):
    parser = StaticHTML()
    parser.feed(source)
    result = ''.join(parser.parts)
    policy = '<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="' + escape(HTML_CSP, quote=True) + '">'
    # HTML is a readable structural view. The parser image remains the sole
    # canvas for P1/P3 pixel boxes, so no clipping or inferred boxes are added.
    presentation = '<style>.document-page{height:auto!important;min-height:0!important;overflow:visible!important}.document-page__content{transform:none!important}mark[data-review-quote]{background:#fff0a8;color:inherit;outline:1px solid #997400}</style>'
    if re.search(r'<head(?:\s[^>]*)?>', result):
        result = re.sub(r'(<head(?:\s[^>]*)?>)', lambda match: match[1] + policy, result, count=1)
        result = result.replace('</head>', presentation + '</head>', 1)
    else:
        result = '<!doctype html><html><head>' + policy + presentation + '</head><body>' + result + '</body></html>'
    return result
