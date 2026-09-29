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

    assert writer.write(BRIEF, ["1.4.2"], "update_existing_material", ask=ask) is None
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
