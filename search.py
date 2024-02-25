import sqlite3
from pprint import pprint
from typing import NamedTuple


import re
import textwrap
import sys


class SearchResult(NamedTuple):
    text: str
    page_number: int
    chapter_title: str
    book_title: str


def run_query(database_path: str, match_text: str) -> list[SearchResult]:
    # Connect to the SQLite database
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    # SQL query to execute
    query = """
    SELECT 
        tb.text AS text,
        tb.page AS page_number,
        c.text AS chapter_title,
        b.title AS book_title
    FROM 
        text_search AS ts
        INNER JOIN text_blocks AS tb ON ts.rowid = tb.id
        INNER JOIN chapters AS c ON tb.chapter_id = c.id
        INNER JOIN books AS b ON c.book_id = b.id
    WHERE 
        ts.text MATCH ?
    ;
    """

    try:
        cursor.execute(query, (match_text,))
        # Fetch all results
        rows = cursor.fetchall()

        # Map the results to the SearchResult named tuple
        results = [SearchResult(*row) for row in rows]
        return results
    finally:
        # Ensure the connection is closed even if an error occurs
        conn.close()


def highlight_search(text: str, search: str) -> str:
    # Define a function to be called for each match
    def replace_func(match):
        return f"====**{match.group(0)}**===="

    # Perform case-insensitive replacement using re.sub
    return re.sub(re.escape(search), replace_func, text, flags=re.IGNORECASE)


def wrap_text(text: str, width: int = 80) -> str:
    return "\n".join(textwrap.wrap(text, width))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: script.py <database_path> <search_term>")
        sys.exit(1)

    database_path = sys.argv[1]
    search = sys.argv[2]

    results = run_query(database_path, search)

    # Print results (for demonstration purposes)
    for result in results:
        print(result.book_title, result.chapter_title, result.page_number)

        # "highlight" the search keyword

        content = wrap_text(highlight_search(result.text, search))
        # display(Markdown(content))
        print(content)
        print("-" * 80)
