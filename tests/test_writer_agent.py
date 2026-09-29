"""The writer: it gets told what was wrong, and the rules do not move.

The smallest loop here and the most visible one. Before it, a sentence that dropped a
version number it was told to keep was thrown away without comment and the rule's
sentence printed instead. The model never learned what was wrong with it, because
nobody told it.

What these hold is that the second chance is a second chance and not a lower bar: the
same rules on every attempt, and three failures mean the rules write it.

Every model answer is scripted, so nothing here calls out.
"""

import pytest

from src import reading
from src.agents import writer

BRIEF = "Package: langchain\nMust appear, exactly as written: 1.4.2, RetrievalQA"


def scripted(*sentences):
    said, asked = list(sentences), []

    def ask(system, user):
        asked.append(user)
        return {"sentence": said.pop(0)} if said else None

    ask.asked = asked
    return ask


def test_a_sentence_that_passes_first_time_is_not_rewritten():
    ask = scripted("The notebooks still call RetrievalQA, gone in 1.4.2.")

    written = writer.write(BRIEF, ["1.4.2", "RetrievalQA"], "update_existing_material", ask=ask)

    assert written["sentence"] == "The notebooks still call RetrievalQA, gone in 1.4.2."
    assert written["tries"] == 1 and written["complaints"] == []
    assert len(ask.asked) == 1


def test_a_dropped_fact_is_named_and_the_rewrite_is_kept():
    ask = scripted("Update the chapter, there have been several releases.",
                   "The notebooks still call RetrievalQA, removed in 1.4.2.")

    written = writer.write(BRIEF, ["1.4.2", "RetrievalQA"], "update_existing_material", ask=ask)

    assert written["tries"] == 2
    # the complaint has to say which facts, or the rewrite is a guess
    assert '"1.4.2"' in ask.asked[1] and '"RetrievalQA"' in ask.asked[1]
    assert "thrown away" in ask.asked[1]


def test_a_contradiction_is_quoted_back():
    ask = scripted("langchain 1.4.2 is out but chapter C8 is up to date.",
                   "Chapter C8 still teaches the API that 1.4.2 removed.")

    written = writer.write(BRIEF, ["1.4.2"], "update_existing_material", ask=ask)

    assert written["tries"] == 2
    assert '"up to date"' in ask.asked[1] and "says the opposite" in ask.asked[1]


def test_a_sentence_too_long_for_a_card_is_sent_back_with_the_number():
    ask = scripted(" ".join(["word"] * 60) + " 1.4.2", "Short enough, and 1.4.2 is in it.")

    written = writer.write(BRIEF, ["1.4.2"], "update_existing_material", ask=ask)

    assert written["tries"] == 2
    assert "16 words too long" in ask.asked[1]


def test_three_failures_leave_it_to_the_rules():
    ask = scripted(*["Update the chapter, several releases landed."] * 4)

    written = writer.write(BRIEF, ["1.4.2"], "update_existing_material", ask=ask)
    # it gave up on the rules, and says so: that is not the same as the model saying nothing
    assert written["sentence"] is None and written["tries"] == 3 and len(written["complaints"]) == 3
    assert len(ask.asked) == 3


def test_the_rewrite_is_held_to_the_same_rules_as_the_first_try():
    # the second answer fixes the fact and breaks the verdict instead
    ask = scripted("Update the chapter, several releases landed.",
                   "langchain 1.4.2 landed and the chapter is up to date.",
                   "The chapter teaches an API 1.4.2 removed.")

    written = writer.write(BRIEF, ["1.4.2"], "update_existing_material", ask=ask)

    assert written["tries"] == 3
    assert len(written["complaints"]) == 2
    assert "You left out" in written["complaints"][0]
    assert "says the opposite" in written["complaints"][1]


def test_watching_is_allowed_to_say_nothing_needs_doing():
    ask = scripted("Patch releases only, so the chapter is up to date.")

    written = writer.write(BRIEF, [], "watch", ask=ask)

    assert written["tries"] == 1


def test_a_model_that_says_nothing_ends_it():
    assert writer.write(BRIEF, [], "watch", ask=lambda system, user: None) is None
    assert writer.write(BRIEF, [], "watch", ask=lambda system, user: {"sentence": "   "}) is None


@pytest.mark.parametrize("sentence, broken", [
    ("Update the chapter.", "You left out"),
    ("1.4.2 landed and RetrievalQA is gone, no action needed.", "says the opposite"),
    (" ".join(["word"] * 50) + " 1.4.2 RetrievalQA", "words too long"),
])
def test_what_each_complaint_says(sentence, broken):
    said = writer.faults(sentence, ["1.4.2", "RetrievalQA"], "update_existing_material")
    assert any(broken in line for line in said)


def test_a_negated_contradiction_is_not_a_contradiction():
    assert writer.faults("The chapter is not up to date with 1.4.2.", ["1.4.2"], "x") == []


def test_the_rules_are_reachable_where_the_pipeline_looks_for_them():
    # reading.py has always been where these live for the rest of the pipeline
    assert reading.keeps_the_facts is writer.keeps_the_facts
    assert reading.contradicts_the_verdict is writer.contradicts_the_verdict
    assert reading.WRITE_SYSTEM == writer.WRITE_SYSTEM


def test_under_forty_five_words_means_under():
    forty_four = " ".join(["word"] * 43) + " 1.4.2"
    forty_five = forty_four + " more"

    assert writer.too_long(forty_four) == 0
    assert writer.too_long(forty_five) == 1
    assert "1 word too long" in " ".join(writer.faults(forty_five, [], "update_existing_material"))


def test_two_sentences_at_most_is_a_rule_it_is_held_to():
    three = "Update the chapter. RetrievalQA is gone in 1.4.2. The notebooks call it."
    said = " ".join(writer.faults(three, ["1.4.2"], "update_existing_material"))

    assert "3 sentences" in said
    assert writer.faults("Update the chapter for 1.4.2. RetrievalQA is gone.", ["1.4.2"],
                         "update_existing_material") == []


def test_the_retry_shows_the_sentence_it_threw_away():
    # Each call is its own conversation, so "keep what was right" meant nothing unless
    # the sentence it is keeping from is in front of it.
    ask = scripted("Update the chapter, several releases landed.",
                   "The notebooks still call RetrievalQA, gone in 1.4.2.")

    writer.write(BRIEF, ["1.4.2", "RetrievalQA"], "update_existing_material", ask=ask)

    assert "Update the chapter, several releases landed." in ask.asked[1]


def test_the_page_is_told_whether_the_model_said_nothing_or_the_rules_refused_it(capsys, monkeypatch):
    monkeypatch.setattr(reading.model, "available", lambda: True)

    monkeypatch.setattr(reading.writer, "write", lambda *args, **kwargs: None)
    assert reading.write_recommendation("langchain", "update_existing_material", "C8", 3, 1, 3.5) is None
    assert "wrote nothing" in capsys.readouterr().out

    monkeypatch.setattr(reading.writer, "write",
                        lambda *args, **kwargs: {"sentence": None, "tries": 3, "complaints": ["x"]})
    assert reading.write_recommendation("langchain", "update_existing_material", "C8", 3, 1, 3.5) is None
    assert "passed the rules" in capsys.readouterr().out
