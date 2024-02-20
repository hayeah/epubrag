import os
import glob
from lxml import etree

from typing import Iterator, Optional
from bs4 import BeautifulSoup
from functools import cached_property, cache
from urllib.parse import urlparse

from typing import NamedTuple, List
from pprint import pprint 

class Chapter(NamedTuple):
    """
    A chapter in an EPUB.
    """

    # chapter index within a book
    index: int 
    href: str
    text: str
    path: str

class TextBlock(NamedTuple):
    """
    A block of text in an EPUB chapter.
    """
    # text block index within a chapter
    chapter: Chapter

    fm: bool

    index: int
    page: int
    dom: BeautifulSoup
    text: str
    

from enum import IntEnum

class PageType(IntEnum):
    FRONTMATTER = 1
    BODY = 2
    ERROR = 3


def roman_to_int(s: str) -> int:
    roman_map: dict[str, int] = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    total: int = 0
    prev_value: int = 0
    
    for char in reversed(s):
        if char not in roman_map:
            raise ValueError("Invalid Roman numeral")
        value: int = roman_map[char]
        if value < prev_value:
            total -= value
        else:
            total += value
        prev_value = value
    
    return total

def parse_pagenumber(input_str: str) -> tuple[int, PageType]:
    # Try parsing as an integer
    try:
        return int(input_str), PageType.BODY
    except ValueError:
        pass  # Not an integer, try parsing as a Roman numeral

    # Try parsing as a Roman numeral
    try:
        return roman_to_int(input_str), PageType.FRONTMATTER
    except ValueError:
        pass  # Not a valid Roman numeral

    # If neither parsing succeeded, return 0
    return 0, PageType.ERROR

# # \xa0 is actually non-breaking space in Latin1 (ISO 8859-1), also chr(160). You should replace it with a space.    
    
# # TODO: detect encoding? but actually, it looks like the xml themselves
# # specifies the encoding as utf8. So maybe it's the tool that's generating these
# # EPUBs confuding the encodings
    
def href_pathonly(href: str) -> str:
    """
    Extract the path from an href.
    """
    parsed = urlparse(href)
    return parsed.path

class ChapterScraper():
    def __init__(self, chapter: Chapter):
        self.chapter = chapter

    @cached_property
    def dom(self) -> BeautifulSoup:
        """
        Open the chapter in bs4.
        """
        with open(self.chapter.path, 'r', encoding='utf-8') as file:
            soup = BeautifulSoup(file, 'xml')
        return soup

    def blocks(self):
        """
        Get the blocks of text from the chapter.
        """

        # direct children (p, div) of body
        # return self.dom.select('body > p, body > div')
        return self.dom.select('body > *')
    

class EPUBScraper:
    def __init__(self, rootdir: str):
        self.rootdir = rootdir

    @cached_property
    def opf_dom(self) -> BeautifulSoup:
        """
        Glob the opf file and open in bs4.
        """
        opf_files = glob.glob(f'{self.rootdir}/*.opf')
        if not opf_files:
            raise FileNotFoundError("No .opf file found in the EPUB directory.")

        opf_path = opf_files[0]  # Assuming there's only one .opf file
        with open(opf_path, 'r', encoding='utf-8') as file:
            soup = BeautifulSoup(file, 'xml')  # Use 'xml' parser for XML/OPF files
        return soup
    
    @cached_property
    def nav_path(self) -> str:
        """
        Get the path to the navigation file.
        """

        toc_reference = self.opf_dom.find('guide').find('reference', type='toc')
        href = toc_reference['href']
        path_only = href_pathonly(href)

        return os.path.join(self.rootdir, path_only)
    
    @cached_property
    def nav_dom(self) -> BeautifulSoup:
        """
        Open the navigation file in bs4.
        """
        with open(self.nav_path, 'r', encoding='utf-8') as file:
            soup = BeautifulSoup(file, 'html.parser')
        return soup
    
    @cached_property
    def chapters(self) -> list[Chapter]:
        """
        Get the chapters from the navigation file.
        """
        links = self.nav_dom.select(".toc_chap a.hlink")

        # use less specific selector if no chapters found
        if len(links) == 0:
            links = self.nav_dom.select("a.hlink")

        relative_root = os.path.dirname(self.nav_path)

        # extract href and text
        chapters = []
        i = 0
        for link in links:
            href = link['href']
            text = link.text.strip()
            chapters.append(Chapter(i, href, text, os.path.join(relative_root, href_pathonly(href))))
            i += 1

        return chapters
    
    # @cached
    def chapter_scraper(self, i) -> ChapterScraper:
        return ChapterScraper(self.chapters[i])
    
    # returns an iterator of TextBlock
    def text_blocks(self) -> Iterator[TextBlock]:
        page: int = int(0)
        fm: bool = False

        for chapter in self.chapters:
            scraper = ChapterScraper(chapter)
            for i, block in enumerate(scraper.blocks()):
                # try to find page number by parsing '<a id="page55">'
                pagetag = block.find('a', id=lambda x: x and x.startswith('page'))
                if pagetag:
                    pagestr = pagetag['id'][4:].upper()
                    nextpage, pagetype = parse_pagenumber(pagestr)
                    if pagetype == PageType.BODY:
                        page = nextpage
                        fm = False
                    elif pagetype == PageType.FRONTMATTER:
                        page = nextpage
                        fm = True

                # not sure if there is a better way to remove <br> tags...
                for br in block.find_all('br'):
                    br.replace_with('\n')
                
                text = block.get_text(separator='').strip()

                # text = block.get_text(separator=' ')
                if len(text) == 0:
                    continue

                yield TextBlock(chapter=chapter, fm=fm, index=i, dom=block, page=page, text=text)




from zipfile import ZipFile
def extract_epub(epub_path: str, output_dir: Optional[str] = None) -> None:
    """
    Extracts an EPUB file to the specified directory.

    :param epub_path: Path to the EPUB file.
    :param output_dir: Directory where the EPUB contents will be extracted. If None, extracts to a folder named after the EPUB file.
    """
    if output_dir is None:
        # If no output directory is specified, create one based on the EPUB file name (without extension).
        output_dir = os.path.splitext(os.path.basename(epub_path))[0]
        output_dir = os.path.join(os.path.dirname(epub_path), output_dir)

    os.makedirs(output_dir, exist_ok=True)

    with ZipFile(epub_path, 'r') as epub:
        epub.extractall(output_dir)
        print(f"EPUB content extracted to: {output_dir}")




# extract_epub('Master Of The Senate (Robert A. Caro) (Z-Library).epub')
epub = EPUBScraper('Master Of The Senate (Robert A. Caro) (Z-Library)')
# epub = EPUBScraper('Means Of Ascent (Robert A. Caro) (Z-Library)')

# print(epub.opf_dom)
# print(epub.nav_path)
# print(epub.nav_dom)
# pprint(epub.chapters)

for block in epub.text_blocks():
    # pprint(block)
    print(block.text)
    print('-' * 80)
    if block.chapter.index > 2:
        break
