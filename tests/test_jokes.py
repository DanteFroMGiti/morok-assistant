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


def test_picker_uses_every_joke_before_repeating_and_resumes_after_restart(tmp_path) -> None:
    history = tmp_path / "joke-history.json"
    jokes = [f"Joke {index}" for index in range(14)]
    picker = JokePicker(Random(7), history)
    first = [picker.choose(jokes) for _ in range(5)]
    assert len(set(first)) == 5

    resumed = JokePicker(Random(11), history)
    rest = [resumed.choose(jokes) for _ in range(9)]
    assert set(first + rest) == set(jokes)
    assert len(set(first + rest)) == 14
    assert resumed.choose(jokes) != rest[-1]
    assert history.stat().st_mode & 0o777 == 0o600


def test_picker_adds_new_jokes_without_restarting(tmp_path) -> None:
    file = tmp_path / "jokes.txt"
    file.write_text("First\n\nSecond\n", encoding="utf-8")
    repository = JokeRepository(file)
    picker = JokePicker(Random(3))
    first = picker.choose(repository.load())

    file.write_text("First\n\nSecond\n\nThird\n", encoding="utf-8")
    next_jokes = [picker.choose(repository.load()) for _ in range(2)]
    assert {first, *next_jokes} == {"First", "Second", "Third"}
