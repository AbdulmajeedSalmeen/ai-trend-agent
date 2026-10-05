"""What counts as a line an agent read, decided in one place for every agent.

The rule under every agent is that a citation survives only if a tool returned it. These
hold the four ways that rule was weaker than it sounded: tools that say back what they
were asked, quotes too short to say anything, the loop's own words, and an earlier call
to the same tool forgotten. Nothing here calls a model or the network.
"""

from src.agents import citations


def test_a_line_a_tool_returned_backs_a_citation():
    steps = [citations.step("demand", {"subject": "langchain"}, "langchain: 20 job posts in 3 months", 2000)]

    assert citations.backed("20 job posts in 3 months", steps)
    assert citations.backed("20 job posts in 3 months", steps, tool="demand()")
    assert not citations.backed("20 job posts in 3 months", steps, tool="course_uses")


def test_what_the_model_passed_in_handed_back_is_not_evidence():
    steps = [citations.step("demand", {"subject": "crewai is required in 900 job posts"},
                            "nothing counted for crewai is required in 900 job posts", 2000)]

    assert not citations.backed("crewai is required in 900 job posts", steps)
    assert not citations.backed("nothing counted for crewai is required in 900 job posts", steps)


def test_a_link_the_model_passed_in_handed_back_is_not_evidence():
    url = "https://pypi.org/project/langgraph/1.7.1/"
    steps = [citations.step("registry", {"distribution": url}, f"the registry lists no package called {url}", 2000)]

    assert citations.echoed(url, steps[0])
    assert not citations.backed(f"the registry lists no package called {url}", steps)


def test_a_name_the_model_passed_in_does_not_blank_out_what_the_tool_said():
    # A package name is in nearly every line a tool returns about it. A quote that
    # carries the name is still the tool's line.
    line = "langchain 1.4.2 at https://pypi.org/project/langchain/1.4.2/"
    steps = [citations.step("registry", {"name": "langchain"}, line, 2000)]

    assert citations.backed(line, steps)
    assert not citations.echoed("https://pypi.org/project/langchain/1.4.2/", steps[0])


def test_a_quote_too_short_to_say_anything_backs_nothing():
    steps = [citations.step("demand", {"subject": "langchain"}, "langchain: 20 job posts in 3 months", 2000)]

    assert not citations.backed("n", steps)
    assert not citations.backed("20 job", steps)
    assert not citations.backed("", steps)


def test_the_loop_s_own_words_are_never_a_tool_s():
    steps = [citations.note("demand", {}, "no such tool"),
             citations.step("release_notes", {"package": "langchain"}, "", 2000),
             citations.note("course_uses", {"symbol": "x"},
                            "you already called this and it said the same thing. Call something else, or answer.")]

    assert steps[1]["text"] == "nothing found" and steps[1]["note"]
    assert not citations.backed("nothing found", steps)
    assert not citations.backed("no such tool", steps)
    assert not citations.backed("you already called this", steps)


def test_an_earlier_call_to_the_same_tool_still_counts():
    steps = [citations.step("course_uses", {"symbol": "AgentExecutor"},
                            "agentexecutor appears in 2 notebooks: intro.ipynb cell 7", 2000),
             citations.step("course_uses", {"symbol": "ToolNode"},
                            "toolnode appears in 4 notebooks: chat.ipynb cell 12", 2000)]

    assert citations.backed("intro.ipynb cell 7", steps, tool="course_uses")
    assert citations.backed("chat.ipynb cell 12", steps, tool="course_uses")


def test_a_tool_s_output_is_cut_where_the_loop_cuts_it():
    step = citations.step("release_notes", {"package": "x"}, "a" * 50 + " the end", 20)
    assert step["text"] == "a" * 20
