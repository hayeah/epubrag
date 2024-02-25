from epub import TextBlock, EPUBScraper, EPUBDBLoader
import glob


epub_db = "epub.db"

epub_files = glob.glob("*.epub")

print(epub_files)


def block_filter(block: TextBlock) -> bool:
    if block.text == "•    •    •":
        return True

    return False


for epubfile in epub_files:
    print(f"Loading: {epubfile}")
    loader = EPUBDBLoader(epub_db)
    loader.load(epubfile, block_filter)
    loader.close()

exit(0)


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
