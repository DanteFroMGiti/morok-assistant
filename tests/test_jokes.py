from random import Random

from morok_assistant.jokes.repository import JokePicker, JokeRepository


def test_jokes_are_loaded_from_separate_blocks_and_reread(tmp_path) -> None:
    path = tmp_path / "jokes.txt"
    path.write_text(
        "# This is a comment\nFirst line\nSecond line\n\n# Another comment\nSecond joke\n",
        encoding="utf-8",
    )
    repository = JokeRepository(path)
    assert repository.load() == ["First line\nSecond line", "Second joke"]

    path.write_text("A new joke\n", encoding="utf-8")
    assert repository.load() == ["A new joke"]


def test_dash_separators_allow_blank_lines_inside_jokes(tmp_path) -> None:
    path = tmp_path / "jokes.txt"
    path.write_text(
        "# A comment\nFirst line\n\nSecond line\n"
        " —————————————————————————————————————————————————— \n"
        "Second joke\n———\n\n# Another comment\nThird joke\n",
        encoding="utf-8",
    )

    assert JokeRepository(path).load() == [
        "First line\n\nSecond line",
        "Second joke",
        "Third joke",
    ]


def test_picker_avoids_repeating_when_more_than_one_joke() -> None:
    picker = JokePicker(Random(7))
    jokes = ["First", "Second"]
    assert picker.choose(jokes) != picker.choose(jokes)
    assert picker.choose([]) is None
