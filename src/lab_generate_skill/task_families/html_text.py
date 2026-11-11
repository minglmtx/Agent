"""Original supplied-copy comparison semantics from admin_text_content."""

from html.parser import HTMLParser
import re


def plain_text(value: object) -> str:
    class Parser(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.parts: list[str] = []
            self.hidden = 0

        def handle_starttag(
            self, tag: str, attrs: list[tuple[str, str | None]]
        ) -> None:
            if tag in ("script", "style"):
                self.hidden += 1
            elif tag in ("p", "div", "br", "li"):
                self.parts.append(" ")

        def handle_endtag(self, tag: str) -> None:
            if tag in ("script", "style"):
                self.hidden = max(0, self.hidden - 1)
            elif tag in ("p", "div", "li"):
                self.parts.append(" ")

        def handle_data(self, data: str) -> None:
            if not self.hidden:
                self.parts.append(data)

    parser = Parser()
    parser.feed(str(value or ""))
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()
