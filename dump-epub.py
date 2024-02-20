import hashlib
import re
import sqlite3
import os
import glob

from typing import Callable, Iterator, Optional
from bs4 import BeautifulSoup
from functools import cached_property
from urllib.parse import urlparse

from typing import NamedTuple
from pprint import pprint

from zipfile import ZipFile

from enum import IntEnum


class Book(NamedTuple):
    hash: str
    title: str
    author: str


class Chapter(NamedTuple):
    """
    A chapter in an EPUB.
    """

    # chapter index within a book
    idx: int
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

    idx: int
    page: int
    dom: BeautifulSoup
    text: str


class PageType(IntEnum):
    FRONTMATTER = 1
    BODY = 2
    ERROR = 3


def file_md5(file_path: str) -> str:
    hash_md5 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def roman_to_int(s: str) -> int:
    s = s.upper()

    roman_map: dict[str, int] = {
        "I": 1,
        "V": 5,
        "X": 10,
        "L": 50,
        "C": 100,
        "D": 500,
        "M": 1000,
    }
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


class ChapterScraper:
    def __init__(self, chapter: Chapter):
        self.chapter = chapter

    @cached_property
    def dom(self) -> BeautifulSoup:
        """
        Open the chapter in bs4.
        """
        with open(self.chapter.path, "r", encoding="utf-8") as file:
            soup = BeautifulSoup(file, "xml")
        return soup

    def blocks(self):
        """
        Get the blocks of text from the chapter.
        """

        # direct children (p, div) of body
        # return self.dom.select('body > p, body > div')
        return self.dom.select("body > *")


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

    with ZipFile(epub_path, "r") as epub:
        epub.extractall(output_dir)
        print(f"EPUB content extracted to: {output_dir}")


class EPUBScraper:
    def __init__(self, epubfile: str):
        self.epubfile = epubfile

        output_dir = os.path.splitext(os.path.basename(epubfile))[0]
        output_dir = os.path.join(os.path.dirname(epubfile), output_dir)

        # root dir of the extracted epub (remove .epub)
        self.rootdir = output_dir

    def extract(self):
        if not os.path.exists(self.rootdir):
            extract_epub(self.epubfile, self.rootdir)

    @cached_property
    def book(self) -> Book:
        return Book(hash=file_md5(self.epubfile), title=self.title, author=self.author)

    @cached_property
    def title(self) -> str:
        return self.opf_dom.find("dc:title").string

    @cached_property
    def author(self) -> str:
        return self.opf_dom.find("dc:creator").string

    @cached_property
    def opf_dom(self) -> BeautifulSoup:
        """
        Glob the opf file and open in bs4.
        """
        opf_files = glob.glob(f"{self.rootdir}/*.opf")
        if not opf_files:
            raise FileNotFoundError("No .opf file found in the EPUB directory.")

        opf_path = opf_files[0]  # Assuming there's only one .opf file
        with open(opf_path, "r", encoding="utf-8") as file:
            soup = BeautifulSoup(file, "xml")  # Use 'xml' parser for XML/OPF files
        return soup

    @cached_property
    def nav_path(self) -> str:
        """
        Get the path to the navigation file.
        """

        toc_reference = self.opf_dom.find("guide").find("reference", type="toc")
        href = toc_reference["href"]
        path_only = href_pathonly(href)

        return os.path.join(self.rootdir, path_only)

    @cached_property
    def nav_dom(self) -> BeautifulSoup:
        """
        Open the navigation file in bs4.
        """
        with open(self.nav_path, "r", encoding="utf-8") as file:
            soup = BeautifulSoup(file, "html.parser")
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
            href = link["href"]
            text = link.text.strip()
            chapters.append(
                Chapter(i, href, text, os.path.join(relative_root, href_pathonly(href)))
            )
            i += 1

        return chapters

    # @cached
    def chapter_scraper(self, i) -> ChapterScraper:
        return ChapterScraper(self.chapters[i])

    # returns an iterator of TextBlock
    # Optional[Callable[[TextBlock], bool]]
    # (TextBlock) -> bool
    def text_blocks(
        self, block_filter: Callable[[TextBlock], bool] = None
    ) -> Iterator[TextBlock]:
        page: int = int(0)
        fm: bool = False

        for chapter in self.chapters:
            scraper = ChapterScraper(chapter)

            i = 0  # index of text block within a chapter
            for block in scraper.blocks():
                # try to find page number by parsing '<a id="page55">'
                pagetag = block.find("a", id=lambda x: x and x.startswith("page"))
                if pagetag:
                    pagestr = pagetag["id"][4:]
                    nextpage, pagetype = parse_pagenumber(pagestr)
                    if pagetype == PageType.BODY:
                        page = nextpage
                        fm = False
                    elif pagetype == PageType.FRONTMATTER:
                        page = nextpage
                        fm = True

                # not sure if there is a better way to remove <br> tags...
                for br in block.find_all("br"):
                    br.replace_with("\n")

                text = block.get_text(separator="").strip()

                # text = block.get_text(separator=' ')
                if len(text) == 0:
                    continue

                text = re.sub(r"\s+", " ", text)

                text_block = TextBlock(
                    chapter=chapter, fm=fm, idx=i, dom=block, page=page, text=text
                )

                # keep the iterator state like page number in this block (if it
                # shows up, but filtering it out, by not incrementing the text
                # block index)
                if block_filter and block_filter(text_block):
                    continue

                yield text_block

                i += 1


SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY,
    hash TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    author TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY,
    book_id INTEGER,
    idx INTEGER NOT NULL,
    href TEXT NOT NULL,
    text TEXT NOT NULL,
    path TEXT NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(id)
);

CREATE TABLE IF NOT EXISTS text_blocks (
    id INTEGER PRIMARY KEY,
    chapter_id INTEGER,
    fm BOOLEAN NOT NULL,
    idx INTEGER NOT NULL,
    page INTEGER NOT NULL,
    text TEXT NOT NULL,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS text_search USING fts5(
    content='text_blocks',
    text
);
"""


def block_filter(block: TextBlock) -> bool:
    if block.text == "•    •    •":
        return True

    return False


class EpubDBLoader:
    def __init__(self, dbstr: str) -> None:
        self.db = sqlite3.connect(dbstr)
        pass

    def load_schema(self):
        self.db.executescript(SCHEMA)
        self.db.commit()

    def load(self, epubfile: str):
        self.load_schema()

        epub = EPUBScraper(epubfile)
        epub.extract()

        # The lastrowid attribute in SQLite (and by extension, in Python's
        # sqlite3 module) refers to the row ID of the last row that was inserted
        # into the database. In the context of SQLite, if you have a table with
        # a column declared as INTEGER PRIMARY KEY, SQLite uses this column as
        # an alias for the rowid. Thus, in such cases, lastrowid will give you
        # the value of the primary key for the last inserted row.

        try:
            cursor = self.db.cursor()

            book = epub.book
            cursor.execute(
                "INSERT INTO books (hash, title, author) VALUES (?, ?, ?)",
                (book.hash, book.title, book.author),
            )
            book_id = cursor.lastrowid

            last_chapter_idx = -1
            chapter_id = 0
            for block in epub.text_blocks(block_filter):
                if block.chapter.idx > last_chapter_idx:
                    last_chapter_idx = block.chapter.idx

                    cursor.execute(
                        """
                        INSERT INTO chapters (book_id, idx, href, text, path)
                        VALUES (:book_id, :idx, :href, :text, :path)
                        """,
                        {
                            "book_id": book_id,
                            **block.chapter._asdict(),
                        },
                    )

                    chapter_id = cursor.lastrowid

                cursor.execute(
                    """
                    INSERT INTO text_blocks (chapter_id, fm, idx, page, text)
                    VALUES (:chapter_id, :fm, :idx, :page, :text)
                    """,
                    {
                        "chapter_id": chapter_id,
                        **block._asdict(),
                    },
                )

                block_id = cursor.lastrowid

                cursor.execute(
                    "INSERT INTO text_search (rowid, text) VALUES (?, ?)",
                    (block_id, block.text),
                )

            self.db.commit()

        except sqlite3.Error as e:
            print(f"SQLITE Error: {e}")
            self.db.rollback()

    def close(self):
        self.db.close()


epub_db = "epub.db"

# epub_files = glob.glob("*.epub")

# for epubfile in epub_files:
#     print(f"Loading: {epubfile}")
#     loader = EpubDBLoader(epub_db)
#     loader.load(epubfile)
#     loader.close()


# means of ascent is maybe a bit shorter than expected..?
# epub = EPUBScraper("Master Of The Senate (Robert A. Caro) (Z-Library).epub")
epub = EPUBScraper("The Path To Power (Robert A. Caro).epub")
# epub.extract()

# print(epub.opf_dom)
# print(epub.nav_path)
# print(epub.nav_dom)
# pprint(epub.chapters)
# print(epub.book)


for block in epub.text_blocks(block_filter):
    if block.chapter.idx > 2:
        break

    # pprint(block)
    print(block.text)
    print("-" * 80)
