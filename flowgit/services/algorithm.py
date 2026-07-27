import difflib
from typing import List, Tuple, Literal


def get_content_difference_difflib(old_content: str, new_content: str) -> List[Tuple[Literal['equal', 'insert', 'delete', 'replace'], int, int]]:
    """
    Return list of operations to perform ('equal', 'insert', 'delete')
    """

    old_lines = old_content.split("\n")
    new_lines = new_content.split("\n")

    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    return matcher.get_opcodes()