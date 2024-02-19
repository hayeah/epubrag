import os
import glob
from lxml import etree

from typing import Optional
from bs4 import BeautifulSoup
from functools import cached_property, cache
from urllib.parse import urlparse

from typing import NamedTuple, List
from pprint import pprint 

class Chapter(NamedTuple):
    """
    A chapter in an EPUB.
    """
    href: str
    text: str
    path: str


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
        return self.dom.select('body > p, body > div')
    

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
        for link in links:
            href = link['href']
            text = link.text.strip()
            chapters.append(Chapter(href, text, os.path.join(relative_root, href_pathonly(href))))

        return chapters
    
    # @cached
    def chapter_scraper(self, i) -> ChapterScraper:
        return ChapterScraper(self.chapters[i])

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




extract_epub('Master Of The Senate (Robert A. Caro) (Z-Library).epub')
epub = EPUBScraper('Master Of The Senate (Robert A. Caro) (Z-Library)')
# epub = EPUBScraper('Means Of Ascent (Robert A. Caro) (Z-Library)')

# print(epub.opf_dom)
print(epub.nav_path)
print(epub.nav_dom)


pprint(epub.chapters)

ch1 = epub.chapter_scraper(0)

for block in ch1.blocks():
    # why are there wierd link breaks?
    # text = block.text.strip()
    # block.contents
    # print(list(block.strings))
    # print(block.encode(indent_level=None))
    # print(block.encode(formatter=None, indent_level=None))
    # print(block.contents)
    # for c in block.contents:
    #     print(type(c))
    #     print(str(c))
        # print(list(c.stripped_strings))
    print(block.get_text(separator=''))
    # content = block.get_text(separator=' ', strip=True)
    # print(content)
    # print()
    print('-' * 80)

