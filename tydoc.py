#!/usr/bin/env python3
"""
tydoc.py:

Module for typesetting documents in ASCII, LaTeX, and HTML.  Perhaps even CSV!

Simson Garfinkel, 2019-

This python is getting better, but still, please let me clean it up before you copy it.
Documents are stored internally as a python XML Element Tree, with these modifications:

- For many tags, we use a subclass of xml.etree.ElementTree that adds more methods.
- Some metdata that's important for LaTeX is stored as attributes in the nodes.
- Although you *can* use ET.tostring() to generate HTML, this module has a set of rendering
  classes that can save as HTML, MarkDown or LaTeX, and that make prettier HTML.

Special classes to consider:

TyTag - subclass of xml.etree.ElementTree, supports an options
        framework that includes round-tripping into HTML. Options are text
        tags that can be added or removed to control how something formats or
        is typeset.

tydoc   - the root element. Typsets as <html>. 
          Includes methods to make it easy to construct complex text documents.
          

tytable - a class for tables. Lots of methods for adding content and formatting.

Output formats:

HTML - It's not just the DOM; we edit it on output to add functionality. But we can round-trip.

LaTeX

Markdown - Generally we follow:
  * https://github.com/adam-p/markdown-here/wiki/Markdown-Cheatsheet#links


Rendering System:

top-level rendering is done with a function called render(doc,f, format)
The TyTag has a convenience method .render(self, f, format) that simply calls render().
render() recursively renders the tree in the requested format to file f.

To render, we walk the tree. 
  - For each tag:
    - If the tag has a CUSTOM RENDERER attribute, call that attribute as a function
      and return. This allows custom tags to control their rendering and avoid the entire machinery. 
    - If the tag declares a function called write_tag_begin() to create the start-string for the tag:
      -  it is called. 
         - If it returns a result, the result emitted.
      - Otherwise, the renderer's class write_tag_begin() is called to come up with the text 
        that is produced as the beginning of the tag. 
      
    - The renderer's text function is called for the tag's text.
    - Each of the tag's children are rendered recursively
    - Renderer's text funciton is called for the tag's tail text.

    - If the tag declares a function called write_tag_end() to create the end-string for the tag:
      -  it is called. 
         - If it returns a result, the result emitted.
      - Otherwise, the renderer's class write_tag_end() is called to come up with the text 
        that is produced as the beginning of the tag. 
"""

__version__ = "0.1.0"

import xml.etree.ElementTree
import xml.etree.ElementTree as ET
import copy
import io
import base64
import codecs
import os
import os.path
import sys
import uuid

sys.path.append( os.path.dirname(__file__))
from latex_tools import latex_escape

TAG_HEAD = 'HEAD'
TAG_BODY = 'BODY'
TAG_P    = 'P'
TAG_B    = 'B'
TAG_I    = 'I'
TAG_H1   = 'H1'
TAG_H2   = 'H2'
TAG_H3   = 'H3'
TAG_HTML = 'HTML'
TAG_PRE  = 'PRE'
TAG_TR   = 'TR'
TAG_TH   = 'TH'
TAG_TD   = 'TD'
TAG_UL   = 'UL'
TAG_LI   = 'LI'
TAG_TABLE = 'TABLE'
TAG_TITLE = 'TITLE'
TAG_CAPTION = 'CAPTION'
TAG_THEAD = 'THEAD'
TAG_TBODY = 'TBODY'
TAG_TFOOT = 'TFOOT'
TAG_TOC   = 'X-TOC'             # a custom tag; should not appear in output

ATTR_VAL = 'v'                # where we keep the original values
ATTR_TYPE = 't'              # the Python type of the value

ATTRIB_OPTIONS = 'OPTIONS'
ATTRIB_ALIGN   = 'ALIGN'

FORMAT_HTML = 'html'
FORMAT_LATEX = 'latex'
FORMAT_TEX   = 'tex'
FORMAT_MARKDOWN = 'md'

CUSTOM_RENDERER = 'custom_renderer'
CUSTOM_WRITE_TEXT = 'custom_write_text'

# Automatically put a newline in the HTML stream after one of these tag blocks

HTML_NO_NEWLINE_TAGS = set([TAG_B,TAG_I,TAG_TD,TAG_TH])

LATEX_TAGS = {TAG_P:('\n','\n\n'),
              TAG_PRE:('\\begin{Verbatim}\n','\n\\end{Verbatim}\n'),
              TAG_B:('\\textbf{','}'),
              TAG_I:('\\textit{','}'),
              TAG_H1:('\\section{','}\n'),
              TAG_H2:('\\subsection{','}\n'),
              TAG_H3:('\\subsubsection{','}\n'),
              TAG_HEAD:('',''),
              TAG_BODY:('',''),
              TAG_TITLE:('\\title{','}\n\\maketitle\n')
              }

MARKDOWN_TAGS = {TAG_HTML:('',''),
                 TAG_PRE:("```","```"),
                 TAG_TITLE:('# ','\n'),
                 TAG_P:('','\n\n'),
                 TAG_B:('**','**'),
                 TAG_H1:('# ','\n'),
                 TAG_H2:('## ','\n'),
                 TAG_H3:('### ','\n'),
                 TAG_HEAD:('',''),
                 TAG_BODY:('','')
                 }

# For the Python
OPTION_LONGTABLE = 'longtable' # use LaTeX {longtable} environment
OPTION_TABLE     = 'table'    # use LaTeX {table} enviornment
OPTION_TABULARX  = 'tabularx' # use LaTeX {tabularx} environment
OPTION_CENTER    = 'center'   # use LaTeX {center} environment
OPTION_NO_ESCAPE = 'noescape' # do not escape LaTeX values
OPTION_SUPPRESS_ZERO    = "suppress_zero" # suppress zeros
OPTION_DATATABLES = 'datatables' # 
OPTION_TOC       = 'toc'         #  automatically create a TOC

LATEX_COLSPEC    = 'latex_colspec'

ATTRIB_TEXT_FORMAT = 'TEXT_FORMAT'
ATTRIB_NUMBER_FORMAT = 'NUMBER_FORMAT'
ATTRIB_INTEGER_FORMAT = 'INTEGER_FORMAT'
ATTRIB_FONT_SIZE   = 'FONTSIZE'
ATTRIB_TITLE       = 'TITLE'
ATTRIB_FOOTER      = 'FOOTER'
ATTRIB_LABEL       = 'LABEL'

ALIGN_LEFT   = "LEFT"
ALIGN_CENTER = "CENTER"
ALIGN_RIGHT  = "RIGHT"

DEFAULT_ALIGNMENT_NUMBER = ALIGN_RIGHT
DEFAULT_ALIGNMENT_STRING = ALIGN_LEFT

DEFAULT_TEXT_FORMAT = '{}'
DEFAULT_NUMBER_FORMAT = '{:,}'
DEFAULT_INTEGER_FORMAT = '{:,}'

class Renderer:
    @staticmethod
    def format():
        return None

    # By default, we write the tag as is repr()
    @staticmethod
    def write_tag_begin(doc, f):
        f.write(f'{repr(doc)}\n')
        return True

    # Default write_text just writes the text
    @staticmethod
    def write_text(doc, f, text=None):
        if text is None:
            text = doc.text
        if text is not None:
            f.write(text)
        return True

    # By default, we write that we are at the end of the tag
    @staticmethod
    def write_tag_end(doc, f):
        f.write(f'--- end repr(doc) ---\n')
        return True

    @staticmethod
    def write_tail(doc, f, tail=None):
        Renderer.write_tail(doc,f,tail)


class HTMLRenderer(Renderer):
    @staticmethod
    def format(self):
        return FORMAT_HTML
    @staticmethod
    def write_tag_begin(doc, f):
        if doc.attrib:
            attribs = (" " + " ".join([f'{key}="{value}"' for (key,value) in doc.attrib.items()]))
        else:
            attribs = ''
        f.write(f'<{doc.tag}{attribs}>')
        return True
    @staticmethod
    def write_tag_end(doc, f):
        f.write(f'</{doc.tag}>')
        if doc.tag.upper() not in HTML_NO_NEWLINE_TAGS:
            f.write("\n")
        return True
    @staticmethod
    def write_tail(doc, f, tail=None):
        HTMLRenderer.write_tail(doc,f,tail)


class LatexRenderer(Renderer):
    @staticmethod
    def format(self):
        return FORMAT_LATEX
    @staticmethod
    def write_tag_begin(doc, f):
        (begin,end) = LATEX_TAGS[doc.tag.upper()]
        f.write(begin)
        return True
    @staticmethod
    def write_text(doc, f, text=None):
        if text is None:
            text = doc.text
        if text is not None:
            if hasattr(doc,'option') and doc.option( OPTION_NO_ESCAPE):
                f.write( latex_escape( text ) )
            else:
                f.write( text )

    @staticmethod
    def write_tag_end(doc, f):
        (begin,end) = LATEX_TAGS[doc.tag.upper()]
        f.write(end)
        return True

    @staticmethod
    def write_tail(doc, f, tail=None):
        LatexRenderer.write_tail(doc,f,tail)

class MarkdownRenderer(Renderer):
    @staticmethod
    def format(self):
        return FORMAT_MARKDOWN
    @staticmethod
    def write_tag_begin(doc, f):
        (begin,end) = MARKDOWN_TAGS[doc.tag.upper()]
        f.write(begin)
        return True
    @staticmethod
    def write_tag_end(doc, f):
        (begin,end) = MARKDOWN_TAGS[doc.tag.upper()]
        f.write(end)
        return True

    
RENDERERS = {FORMAT_HTML:     HTMLRenderer(),
             FORMAT_LATEX:    LatexRenderer(),
             FORMAT_TEX:      LatexRenderer(),
             FORMAT_MARKDOWN: MarkdownRenderer()}

def render(doc, f, format=FORMAT_HTML):
    """Custom rendering tool. Use the built-in rendering unless the
    Element has its own render method. Write results to f, which can
    be a file or an iobuffer"""

    if hasattr(doc,CUSTOM_RENDERER) and doc.custom_renderer(f, format=format):
        return True

    try:
        r = RENDERERS[format]
    except KeyError as e:
        raise RuntimeError("Unsupported format: "+format)

    if not (hasattr(doc,"write_tag_begin") and doc.write_tag_begin(f, format)):
        r.write_tag_begin(doc, f)
        
    if not (hasattr(doc,"write_text") and doc.write_text(f, format)):
        r.write_text(doc, f)
        
    for child in list(doc):
        render(child, f, format)

    if not (hasattr(doc,"write_tag_end") and doc.write_tag_end(f, format)):
        r.write_tag_end(doc, f)
        
    if doc.tail is not None:
        if not (hasattr(doc,"write_tail") and doc.write_tail(f, format)):
            r.write_tail(doc, f)
        

################################################################
# some formatting codes
#
def safenum(v):
    """Return v as an int if possible, then as a float, otherwise return it as is"""
    try:
        return int(v)
    except (ValueError, TypeError):
        pass
    try:
        return float(v)
    except (ValueError, TypeError):
        pass
    return v


def scalenum(v, minscale=0):
    """Like safenum, but automatically add K, M, G, or T as appropriate"""
    v = safenum(v)
    if type(v) == int:
        for (div, suffix) in [[1_000_000_000_000, 'T'],
                              [1_000_000_000, 'G'],
                              [1_000_000, 'M'],
                              [1_000, 'K']]:
            if (v > div) and (v > minscale):
                return str(v // div) + suffix
    return v


################################################################

class TyTag(xml.etree.ElementTree.Element):
    def __init__(self, tag, attrib={}, **extra):
        super().__init__(tag, attrib, **extra)

    def render(self,f, format='html'):
        return render(self, f, format=format)
    
    def save(self,f_or_fname,format=None,**kwargs):
        """Save to a filename or a file-like object"""
        if not format:
            format = os.path.splitext(fout)[1].lower()
            if format[0:1]=='.':
                format=format[1:]

        if isinstance(f_or_fname, io.IOBase):
            self.render(f_or_fname, format=format)
            return

        with open(f_or_fname,"w") as f:
            self.render(f, format=format)
            return

    def prettyprint(self):
        s = ET.tostring(self,encoding='unicode')
        return xml.dom.minidom.parseString( s ).toprettyxml(indent='  ')
    
    def options_as_set(self):
        """Return all of the options as a set"""
        try:
            return set(self.attrib[ATTRIB_OPTIONS].split(','))
        except KeyError as e:
            return set()

    def set_option(self, option):
        """@param option is a string that is added to the 'option' attrib. They are separated by commas"""
        options = self.options_as_set()
        options.add(option)
        self.attrib[ATTRIB_OPTIONS] = ','.join(options)

    def clear_option(self, option):
        """@param option is a string that is added to the 'option' attrib. They are separated by commas"""
        options = self.options_as_set()
        options.remove(option)
        self.attrib[ATTRIB_OPTIONS] = ','.join(options)

    def option(self, option):
        """Return true if option is set."""
        return option in self.options_as_set()

    def add(self, tag, *args):
        """Add an element with type 'tag' for each item in args.  If args has
        elements inside it, add them as subelements, with text set to
        the tail. Returns the tag that is added."""

        # Make the tag and add it. The add in the text or sub-tags
        e       = TyTag(tag)
        self.append(e)

        lastTag = None
        for arg in args:
            if not isinstance(arg, ET.Element):
                if lastTag is not None:
                    if lastTag.tail == None:
                        lastTag.tail = ""
                    lastTag.tail  += str(arg)
                else:
                    if e.text == None:
                        e.text = ""
                    e.text += str(arg)
            else:
                # Copy the tag into place
                lastTag = copy.deepcopy(arg)
                e.append(lastTag)
        return e

class EmbeddedImageTag(TyTag):
    def __init__(self, buf, *, format, alt=""):
        """Create an image. You must specify the format. 
        buf can be a string of a BytesIO"""
        super().__init__('img')
        self.buf    = buf
        self.alt    = alt
        self.format = format

    def custom_renderer(self, f, alt="", format=FORMAT_HTML):
        if format==FORMAT_HTML:
            f.write('<img alt="{}" src="data:image/{};base64,{}" />'.format(
                self.alt,self.format,codecs.decode(base64.b64encode(self.buf))))
        elif format in (FORMAT_LATEX, FORMAT_TEX):
            fname = os.path.splitext(f.name)[0]+"_image.png"
            with open(fname,"wb") as f2:
                f2.write(self.buf)
            f.write(f'\\includegraphics{fname}\n')
        raise RuntimeError("unknown format: {}".format(format))
        
class tydoc(TyTag):
    """Python class for building HTML documents and rendering them into
HTML, LaTeX or Markdown.
"""

    # We have a custom begin and end text for latex

    DEFAULT_LATEX_PACKAGES = ['graphicx','tabularx','longtable']
    DEFAULT_META_TAGS=['<meta http-equiv="Content-type" content="text/html; charset=utf-8">']
    def __init__(self, format=None):
        super().__init__(TAG_HTML)
        self.head = self.add(TAG_HEAD)
        self.body = self.add(TAG_BODY)
        self.options = set()
        self.latex_packages=self.DEFAULT_LATEX_PACKAGES

    def write_tag_begin(self, f, format=None):
        """Provide custom tags for writing document tag"""
        if format==FORMAT_LATEX:
            f.write("\n".join(["\\documentclass{article}"] + 
                              ['\\usepackage{%s}\n' % pkg for pkg in self.latex_packages] +
                              ["\\begin{document}"]))
            return True
        elif format==FORMAT_HTML:
            f.write('\n'.join(['<!DOCTYPE html>','<html>'] + self.DEFAULT_META_TAGS))
            f.write('\n')
            return True
        else:
            return False

    def write_tag_end(self, f, format=None):
        if format==FORMAT_LATEX:
            f.write("\\end{document}\n")
            return True
        elif format==FORMAT_HTML:
            f.write('</html>\n')
            return True
        else:
            return False

    def toc_tags(self,level=3):
        """Return a new tytag ('toc') with of the heading tags as necessary,
        up to the specified level.  This could probably be done with
        some clever XPath..."""
        ret = TyTag(TAG_TOC)
        for elem in self.find("./BODY"):
            if elem.tag==TAG_H1 and level>=1:
                ret.append(elem)
            if elem.tag==TAG_H2 and level>=2:
                ret.append(elem)
            if elem.tag==TAG_H3 and level>=3:
                ret.append(elem)
        return ret

    def insert_image(self, buf, *, format):
        if isinstance(buf,io.BytesIO):
            buf.seek(0)
            buf = buf.read()    # turn it into a buffer
        img = EmbeddedImageTag(buf,format=format)
        self.append(img)

    def insert_matplotlib(self, plt, *, format="png", **kwargs):
        buf = io.BytesIO()
        plt.savefig(buf, format=format, **kwargs)
        buf.seek(0)
        self.insert_image(buf,format='png')

    def set_title(self, *text):
        self.head.add(TAG_TITLE, *text)

    def p(self, *text):
        """Add a paragraph. Multiple arguments are combined and can be text or other HTML elements"""
        self.body.add(TAG_P, *text)
        return self
        
    def h1(self, *text):
        """Add a H1"""
        self.body.add(TAG_H1, *text)
        return self

    def h2(self, *text):
        """Add a H2"""
        self.body.add(TAG_H2, *text)
        return self

    def h3(self, *text):
        """Add a H3"""
        self.body.add(TAG_H3, *text)
        return self

    def pre(self, *text):
        """Add a preformatted"""
        self.body.add(TAG_PRE, *text)
        return self

    def table(self, **kwargs):
        t = tytable()
        self.body.append(t)
        return t

    def stylesheet(self, url):
        self.head.append(TyTag('link',{'rel':"stylesheet",
                                       'type':"text/css",
                                       'href':url}))
    def script(self, url):
        self.head.append(TyTag('script',{'type':"text/javascript",
                                         'src':url}))

    def ul(self, *text):
        """Add a UL"""
        self.body.add(TAG_UL, *text)

    def li(self, *text):
        """Add a LI"""
        self.body.add(TAG_UL, *text)




################################################################
### Improved tytable with the new API.
### Class name has changed from ttable to tytable.
### It now uses the XML ETree to represent the table.
### Tables can then be rendered into HTML or another form.
################################################################
class tytable(TyTag):
    """Python class for representing a table that can be rendered into
    HTML or LaTeX or text.  Based on Simson Garfinkel's legacy
    ttable() class, which was a hack that evolved. This class has a
    similar API, but it is a complete rewrite. Most of the old API is 
    preserved, but it's not identical, so the original ttable is available 
    in the tytable.ttable() module. We apologize for the name confusion between
    tytable.ttable() (the ttable class in the typeset-table module) and the 
    tydoc.tytable() class (the typeset table class in the typset document module.)

    Note:

    1. Format for table cells must be specified in advance, and formatting is done
       when data is put into the table.  If format is changed, table
       is reformatted.

    2. Orignal numeric data and type are kept as HTML attribs.

    3. Creating a <table> HTML tag automatically creates child <thead>, <tbody> and <tfoot> nodes.
       Most people don't know that these tags even exist, but the browsers do.
    """

    VALID_ALIGNS = set([ALIGN_LEFT,ALIGN_CENTER,ALIGN_RIGHT])


    @staticmethod
    def cells_in_row(tr):
        return list( filter(lambda t:t.tag in (TAG_TH, TAG_TD), tr) )

    def __init__(self,attrib={},**extra):
        super().__init__('table',attrib=attrib,**extra)
        
        self.options = set()
        self.attrib[ATTRIB_TEXT_FORMAT]    = DEFAULT_TEXT_FORMAT
        self.attrib[ATTRIB_NUMBER_FORMAT]  = DEFAULT_NUMBER_FORMAT
        self.attrib[ATTRIB_INTEGER_FORMAT] = DEFAULT_INTEGER_FORMAT

        # Create the layout of the generic table
        self.add(TAG_CAPTION)
        self.add(TAG_THEAD)
        self.add(TAG_TBODY)
        self.add(TAG_TFOOT)
    
    def custom_renderer(self, f, alt="", format=FORMAT_HTML):
        if format in (FORMAT_LATEX,FORMAT_TEX):
            return self.custom_renderer_latex(f)
        elif format in (FORMAT_MARKDOWN):
            return self.custom_renderer_md(f)
        else:
            return False
        
    def custom_renderer_latex(self,f):
        self.render_latex_table_head(f)
        f.write("\\hline\n")
        self.render_latex_table_body(f)
        f.write("\\hline\n")
        self.render_latex_table_foot(f)
        return True

    def custom_renderer_md(self,f):
        """Output the table as markdown. Assumes the first row is the header."""
        # Calculate the maxim width of each column
        all_cols = [self.col(n) for n in range(self.max_cols())]
        col_maxwidths = [max( [len(str(cell.text)) for cell in col] ) for col in all_cols]
        for (rownumber,tr) in enumerate(self.findall(".//TR"),0):
            # Get the cells for this row
            row_cells = self.cells_in_row(tr)

            # Pad this row out if it needs padding
            # Markdown tables don't support col span
            if len(row_cells) < len(all_cols):
                row_cells.extend([TyTag(TAG_TD)] * (cols-len(row)))

            # Make up the format string for this row based on the cell attributes

            fmts = []
            for (cell,maxwidth) in zip(row_cells,col_maxwidths):
                if cell.attrib.get(ATTRIB_ALIGN,"")==ALIGN_LEFT:
                    align='<'
                elif cell.attrib.get(ATTRIB_ALIGN,"")==ALIGN_CENTER:
                    align='^'
                elif cell.attrib.get(ATTRIB_ALIGN,"")==ALIGN_RIGHT:
                    align='>'
                else:
                    align=''
                fmts.append("{:" + align + str(maxwidth) +"}")
            fmt = "|" + "|".join(fmts) + "|\n"

            # Get the text we will format
            row_texts = [cell.text for cell in row_cells]

            # Write it out, formatted
            f.write(fmt.format(*row_texts))

            # Add a line between the first row and the rest.
            if rownumber==0:
                lines = ['-' * width for width in col_maxwidths]
                f.write(fmt.format(*lines))

        return True             #  we rendered!

    #################################################################
    ### LaTeX support routines
    def latex_cell_text(self,cell):
        if self.option(OPTION_NO_ESCAPE):
            return cell.text
        else:
            return latex_escape(cell.text)

    def render_latex_table_row(self,f,tr):
        """Render the first set of rows that were added with the add_head() command"""
        f.write(' & '.join([self.latex_cell_text(cell) for cell in tr]))
        f.write('\\\\\n')
        
    def render_latex_table_head(self,f):
        if self.option(OPTION_TABLE) and self.option(OPTION_LONGTABLE):
            raise RuntimeError("options TABLE and LONGTABLE conflict")
        if self.option(OPTION_TABULARX) and self.option(OPTION_LONGTABLE):
            raise RuntimeError("options TABULARX and LONGTABLE conflict")
        if self.option(OPTION_TABLE):
            # LaTeX table - a kind of float
            f.write('\\begin{table}\n')
            caption = self.get_caption()
            if caption is not None:
                f.write("\\caption{%s}" % caption)
            try:
                f.write(r"\label{%s}" % id(self)) # always put in ID
                f.write(r"\label{%s}" % self.attrib[ATTRIB_LABEL]) # put in label if provided
            except KeyError:
                pass            # no caption
            f.write("\n")
            if self.option(OPTION_CENTER):
                f.write('\\begin{center}\n')
        if self.option(OPTION_LONGTABLE):
            f.write('\\begin{longtable}{%s}\n' % self.latex_colspec())
            caption = self.get_caption()
            if caption is not None:
                f.write("\\caption{%s}\n" % caption)
            try:
                f.write("\\label{%s}" % id(self)) # always output myid
                f.write("\\label{%s}" % self.attrib[ATTRIB_LABEL])
            except KeyError:
                pass            # no caption
            f.write("\n")
            for tr in self.findall("./THEAD/TR"):
                self.render_latex_table_row(f,tr)
            f.write('\\hline\\endfirsthead\n')
            f.write('\\multicolumn{%d}{c}{(Table \\ref{%s} continued)}\\\\\n' 
                    % (self.max_cols(), id(self)))
            f.write('\\hline\\endhead\n')
            f.write('\\multicolumn{%d}{c}{(continued on next page)}\\\\\n'
                    % (self.max_cols()))
            f.write('\\hline\\endfoot\n')
            f.write('\\hline\\hline\n\\endlastfoot\n')
        else:
            # Not longtable, so regular table
            if self.option(OPTION_TABULARX):
                f.write('\\begin{tabularx}{\\textwidth}{%s}\n' % self.latex_colspec())
            else:
                f.write('\\begin{tabular}{%s}\n' % self.latex_colspec())
            for tr in self.findall("./THEAD/TR"):
                self.render_latex_table_row(f,tr)
            
    def render_latex_table_body(self,f):
        """Render the rows that were not added with add_head() command"""
        for tr in self.findall("./TBODY/TR"):
            self.render_latex_table_row(f,tr)

    def render_latex_table_foot(self,f):
        for tr in self.findall("./TFOOT/TR"):
            self.render_latex_table_row(f,tr)
        if self.option(OPTION_LONGTABLE):
            f.write('\\end{longtable}\n')
        else:
            if self.option(OPTION_TABULARX):
                f.write('\\end{tabularx}\n')
            else:
                f.write('\\end{tabular}\n')
        if self.option(OPTION_CENTER):
            f.write('\\end{center}\n')
        if self.option(OPTION_TABLE):
            f.write('\\end{table}\n')

    def set_caption(self, caption):
        #  TODO: Validate that this is first
        """The <caption> tag must be inserted immediately after the <table> tag.
        https://www.w3schools.com/tags/tag_caption.asp
        """
        self.add(TAG_CAPTION, caption)

    def set_fontsize(self, size):
        self.attrib[ATTRIB_FONT_SIZE] = str(size)

    def set_latex_colspec(self,latex_colspec): 
        """LaTeX colspec is just used when typesetting with latex. If one is
not set, it auto-generated"""

        self.attrib[LATEX_COLSPEC] = latex_colspec

    def latex_colspec(self):
        """Use the user-supplied LATEX COLSPEC; otherwise figure one out"""
        try:
            return self.attrib[LATEX_COLSPEC]
        except KeyError as c:
            return "l"*self.max_cols()

    #################################################################
    ### Cell Formatting Routines

    def format_cell(self, cell):
        """Modify cell by setting its text to be its format. Uses eval, so it's not safe."""
        try:
            typename = cell.attrib[ATTR_TYPE]
            typeval  = cell.attrib[ATTR_VAL]
        except KeyError:
            return cell

        if typename is None:
            return cell

        try:
            value = eval(typename)(typeval)
        except Exception as e:
            return cell
        try:
            if cell.attrib[ATTR_TYPE]=='int':
                cell.text = self.attrib[ATTRIB_INTEGER_FORMAT].format(int(value))
            else:
                cell.text = self.attrib[ATTRIB_NUMBER_FORMAT].format(float(value))
        except ValueError as e:
            cell.text = self.attrib[ATTRIB_TEXT_FORMAT].format(value)
        return cell

    #################################################################
    ### Table Manipulation Routines

    def add_row(self, where, cells, row_attrib={}):
        """Add a row of cells to the table.
        @param cells - a list of cells.
        """
        where_node = self.findall(f".//{where}")[0]
        row = ET.SubElement(where_node,TAG_TR, attrib=row_attrib)
        for cell in cells:
            row.append(cell)

    def add_row_values(self, where, tags, values, *, cell_attribs={}, row_attrib={}):
        """Create a row of cells and add it to the table.
        @param where  - should be TAG_THEAD/TAG_TBODY/TAG_TFOOT
        @param tags   - a single tag, or a list of tags. 
        @param values - a list of values.  Each is automatically formatted.
        @param cell_attribs - a single cell attrib, or a list of attribs
        @param row_attrib - a single attrib for the row, or a list of attribs
        """
        assert where in (TAG_THEAD, TAG_TBODY, TAG_TFOOT)

        # If tags is not a list, make it a list
        if not isinstance(tags,list):
            tags = [tags] * len(values)

        if not isinstance(cell_attribs,list):
            cell_attribs = [cell_attribs] *len(values)

        if not (len(tags)==len(values)==len(cell_attribs)):
            raise ValueError("tags ({}) values ({}) and cell_attribs ({}) must all have same length".format(
                    len(tags),len(values),len(cell_attribs)))
        cells = [self.make_cell(t,v,a) for (t,v,a) in zip(tags,values,cell_attribs)]
        self.add_row(where, cells, row_attrib=row_attrib)
        
    def add_head(self, values, row_attrib={}, cell_attribs={}):
        self.add_row_values(TAG_THEAD, 'TH', values, row_attrib=row_attrib, cell_attribs=cell_attribs)

    def add_data(self, values, row_attrib={}, cell_attribs={}):
        self.add_row_values(TAG_TBODY, 'TD', values, row_attrib=row_attrib, cell_attribs=cell_attribs)

    def add_foot(self, values, row_attrib={}, cell_attribs={}):
        self.add_row_values(TAG_TFOOT, 'TD', values, row_attrib=row_attrib, cell_attribs=cell_attribs)

    def add_data_array(self, rows):
        for row in rows:
            self.add_data(row)

    def make_cell(self, tag, value, attrib):
        """Given a tag, value and attributes, return a cell formatted with the default format"""
        cell = ET.Element(tag,{**attrib,
                                 ATTR_VAL:str(value),
                                 ATTR_TYPE:str(type(value).__name__)
                                 })
        self.format_cell(cell)
        return cell


    ################################################################
    ### Table get information routines

    def get_caption(self):
        """Return the <caption> tag text"""
        try:
            c = self.findall(".//CAPTION")
            return c[0].text
        except (KeyError,IndexError) as e:
            return None

    def rows(self):
        """Return the rows"""
        return self.findall(".//TR")

    def row(self,n):
        """Return the nth row; n starts at 0"""
        return self.rows()[n]

    def max_cols(self):
        """Return the number of maximum number of cols in the data. Expensive to calculate"""
        return max( len(row.findall("*")) for row in self.rows())
        
    def get_cell(self, row, col):
        """Return the cell at row, col; both start at 0"""
        return self.cells_in_row( self.row(row) ) [col]
        
    def col(self,n):
        """Returns all the cells in column n"""
        return [row[n] for row in self.rows()]


################################################################
##
## covers for making it easy to construct HTML
##
################################################################

# Add some covers for popular paragraph types
def p(*text):
    """Return a paragraph. Text runs are combined"""
    return tydoc().p(*text)

def h1(*text):
    """Return a header 1"""
    return tydoc().h1(*text)

def h2(*text):
    """Return a header 2"""
    return tydoc().h2(*text)

def h3(*text):
    """Return a header 3"""
    return tydoc().h3(*text)

def pre(*text):
    """Return preformatted text"""
    return tydoc().pre(*text)

def b(text):
    """Return a bold run"""
    e = ET.Element('b')
    e.text=text
    return e

def i(text):
    """Return an itallic run """
    e = ET.Element('i')
    e.text=text
    return e

def showcase(doc):
    print("---DOM---")
    print(ET.tostring(doc,encoding='unicode'))
    print("\n---HTML---")
    doc.render(sys.stdout, format='html')
    print("\n---LATEX---")
    doc.render(sys.stdout, format='latex')
    print("\n---MD---")
    doc.render(sys.stdout, format='md')
    print("\n==========")

def demo1():
    # Verify that render works
    doc  = ET.fromstring("<html><p>First Paragraph</p><p>Second <b>bold</b> Paragraph</p></html>")
    return doc

def demo2():
    doc = ET.Element("html")
    ET.SubElement(doc, 'p').text = "First Paragraph"

    p = ET.SubElement(doc, 'p')
    p.text = "Second "

    b = ET.SubElement(p, 'b')
    b.text = "bold"
    b.tail = " Paragraph"
    return doc

def demo3():
    b = ET.Element('b')
    b.text = "bold"

    doc = tydoc()
    doc.p("First Paragraph")
    doc.p("Second ",b, " Paragraph")
    return doc

def demo4():
    doc = tydoc()
    doc.p("First Paragraph")
    doc.p("Second ",b('bold'), " Paragraph")
    return doc

def tabdemo1():
    doc = tydoc()
    doc.set_title("Test Document")
    doc.h1("Table demo")

    lcr = [{},{ATTRIB_ALIGN:ALIGN_CENTER},{ATTRIB_ALIGN:ALIGN_RIGHT}]
    lcrr = lcr + [{ATTRIB_ALIGN:ALIGN_RIGHT},{ATTRIB_ALIGN:ALIGN_RIGHT}]

    d2 = doc.table()
    d2.set_option(OPTION_TABLE)
    d2.add_head(['State','Abbreviation','Rank','Population','% Change'])
    d2.add_data(['California','CA',1,37252895,10.0],cell_attribs=lcrr)
    d2.add_data(['Virginia','VA',12,8001045,13.0],cell_attribs=lcrr)

    doc.p("")
    d2 = doc.table()
    d2.set_option(OPTION_LONGTABLE)
    d2.add_head(['State','Abbreviation','Population'],cell_attribs={ATTRIB_ALIGN:ALIGN_CENTER})
    d2.add_data(['Virginia','VA',8001045], cell_attribs=lcr)
    d2.add_data(['California','CA',37252895], cell_attribs=lcr)
    return doc

def datatables():
    doc = tydoc()
    doc.script('https://code.jquery.com/jquery-3.3.1.js')
    doc.script('https://cdn.datatables.net/1.10.19/js/jquery.dataTables.min.js')
    t = doc.table(attrib={'id':'1234'})




if __name__=="__main__":
    # Showcase different ways of making a document and render it each
    # way:
    if False:
        showcase(demo1())
        showcase(demo2())
        showcase(demo3())
        showcase(demo4())
    showcase(tabdemo1())
    exit(0)

