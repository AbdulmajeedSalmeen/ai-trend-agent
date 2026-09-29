"""The verifier: it may raise a claim to two records, and only by reading the second one.

The weakest thing this pipeline calls confirmed is a release page saying what the
release page said. Raising that to a registry match is worth real confidence, so the
agent that does it has to be held to what it actually read: a line that names this
version, from a document a tool returned, at a link a tool printed.

Every model answer is scripted and every fetch is a local function, so nothing here
reaches the network.
"""

from datetime import datetime, timezone

import pytest
import requests

from src.agents import verifier
from src.schema import Claim, Signal
from src.stages import stage2b_verify

RELEASES = ("langchain-ai/langchain releases: langchain-core==1.4.2 at "
            "https://github.com/langchain-ai/langchain/releases/tag/langchain-core%3D%3D1.4.2; "
            "langchain-core==1.4.1 at https://github.com/langchain-ai/langchain/releases/tag/old")


def claim(version="1.4.2"):
    return Claim(text=f"langchain-core version {version} was released", subject="langchain-core",
                 version=version, source_signal_id="pypi_1")


def signal(ident="pypi_1", source="pypi"):
    return Signal(id=ident, source=source, tier=1, subject="langchain-core",
                  title="langchain-core 1.4.2", url="https://pypi.org/project/langchain-core/1.4.2/",
                  published_at=datetime(2026, 9, 21, tzinfo=timezone.utc), body="")


def scripted(*answers):
    said, asked = list(answers), []

    def ask(system, user):
        asked.append(user)
        return said.pop(0) if said else None

    ask.asked = asked
    return ask


def tools():
    return {"registry": lambda distribution="": f"{distribution} is on the registry",
            "releases": lambda repo="": RELEASES,
            "changelog": lambda repo="": f"{repo} keeps no changelog we can find"}


def answer(found=True, url="https://github.com/langchain-ai/langchain/releases/tag/langchain-core%3D%3D1.4.2",
           quote="langchain-core==1.4.2"):
    return {"answer": {"found": found, "url": url, "quote": quote}}


def test_it_goes_looking_and_says_where_it_found_the_version():
    ask = scripted({"tool": "releases", "args": {"repo": "langchain-ai/langchain"}}, answer())

    found = verifier.confirm(claim(), "pypi", tools(), ask=ask)

    assert found["url"].endswith("langchain-core%3D%3D1.4.2")
    assert [step["tool"] for step in found["looked"]] == ["releases"]
    # the answering turn must carry what it read, or the loop is decoration
    assert "langchain-core==1.4.2" in ask.asked[1]


def test_a_line_no_tool_returned_is_refused():
    ask = scripted({"tool": "releases", "args": {"repo": "langchain-ai/langchain"}},
                   answer(quote="the maintainers announced 1.4.2 on their blog"))

    assert verifier.confirm(claim(), "pypi", tools(), ask=ask) is None


def test_a_record_that_does_not_name_this_version_is_a_record_of_something_else():
    ask = scripted({"tool": "releases", "args": {"repo": "langchain-ai/langchain"}},
                   answer(quote="langchain-core==1.4.1", url="https://github.com/langchain-ai/langchain/releases/tag/old"))

    assert verifier.confirm(claim(), "pypi", tools(), ask=ask) is None


def test_a_link_it_was_never_shown_is_refused():
    ask = scripted({"tool": "releases", "args": {"repo": "langchain-ai/langchain"}},
                   answer(url="https://github.com/langchain-ai/langchain/releases/tag/v1.4.2"))

    assert verifier.confirm(claim(), "pypi", tools(), ask=ask) is None


def test_another_page_of_the_record_we_already_hold_is_not_a_second_record():
    # we hold the repository's release; quoting the repository back is not a second party
    ask = scripted({"tool": "releases", "args": {"repo": "langchain-ai/langchain"}}, answer())

    assert verifier.confirm(claim(), "github", tools(), ask=ask) is None


def test_the_registry_answers_a_claim_the_repository_gave_us():
    listed = ("langchain-core is on the registry at https://pypi.org/project/langchain-core/ , "
              "versions listed: 1.4.1, 1.4.2. Each of the newest: "
              "1.4.2 at https://pypi.org/project/langchain-core/1.4.2/")
    kit = {**tools(), "registry": lambda distribution="": listed}
    ask = scripted({"tool": "registry", "args": {"distribution": "langchain-core"}},
                   answer(url="https://pypi.org/project/langchain-core/1.4.2/",
                          quote="1.4.2 at https://pypi.org/project/langchain-core/1.4.2/"))

    found = verifier.confirm(claim(), "github", kit, ask=ask)
    assert found["url"] == "https://pypi.org/project/langchain-core/1.4.2/"


def test_calling_the_same_thing_twice_is_answered_without_calling_it():
    calls = []
    kit = {**tools(), "releases": lambda repo="": calls.append(repo) or RELEASES}
    ask = scripted({"tool": "releases", "args": {"repo": "x/y"}},
                   {"tool": "releases", "args": {"repo": "x/y"}},
                   answer())

    verifier.confirm(claim(), "pypi", kit, ask=ask)
    assert calls == ["x/y"]
    assert "you already called this" in ask.asked[2]


def test_saying_it_found_nothing_is_an_answer():
    ask = scripted({"tool": "changelog", "args": {"repo": "langchain-ai/langchain"}}, answer(found=False))
    assert verifier.confirm(claim(), "pypi", tools(), ask=ask) is None

    assert verifier.confirm(claim(version=None), "pypi", tools(), ask=scripted(answer())) is None


def test_it_cannot_look_forever():
    ask = scripted(*[{"tool": "releases", "args": {"repo": "x/y"}} for _ in range(9)])

    assert verifier.confirm(claim(), "pypi", tools(), ask=ask, max_steps=2) is None
    assert len(ask.asked) == 3


def test_the_registry_tool_gives_the_versions_and_where_the_source_lives():
    payload = {"info": {"project_urls": {"Source": "https://github.com/langchain-ai/langchain"}},
               "releases": {"1.4.1": [], "1.4.2": []}}
    registry = verifier.registry_tool(lambda url: payload if "langchain-core" in url else None)

    said = registry(distribution="langchain-core")
    assert "langchain-ai/langchain" in said and "1.4.2" in said
    assert "https://pypi.org/project/langchain-core/" in said
    assert "lists no package" in registry(distribution="not-a-package")
    assert "name a package" in registry()
    # the help says distribution; a model that writes package has still said which one
    assert "langchain-ai/langchain" in registry(package="langchain-core")


def test_the_releases_tool_prints_a_tag_with_the_link_to_it():
    listing = [{"tag_name": "langchain-core==1.4.2", "html_url": "https://github.com/x/y/releases/tag/a"}]
    releases = verifier.releases_tool(lambda url: listing if "x/y" in url else [])

    assert "langchain-core==1.4.2 at https://github.com/x/y/releases/tag/a" in releases(repo="x/y")
    assert "published no releases" in releases(repo="quiet/repo")
    assert "owner/name" in releases(repo="nolash")
    assert "owner/name" in releases()
    assert "langchain-core==1.4.2" in releases(repository="x/y")


def test_the_changelog_tool_tries_the_usual_names_and_says_which_it_read():
    pages = {"https://raw.githubusercontent.com/x/y/master/CHANGES.md": "## 1.4.2 released today"}
    changelog = verifier.changelog_tool(lambda url: pages.get(url))

    said = changelog(repo="x/y")
    assert "https://github.com/x/y/blob/master/CHANGES.md" in said and "1.4.2" in said
    assert "keeps no changelog" in changelog(repo="a/b")


@pytest.mark.parametrize("tool, kwargs", [("registry", {"distribution": "x"}), ("releases", {"repo": "x/y"}),
                                          ("changelog", {"repo": "x/y"})])
def test_a_source_that_is_down_does_not_end_the_run(tool, kwargs):
    def angry(url):
        raise requests.RequestException("no network")

    kit = verifier.tools_for(json_get=angry, text_get=angry)
    assert "could not be read" in kit[tool](**kwargs)


def test_a_claim_one_document_supports_rises_to_two_when_the_second_is_found():
    ask = scripted({"tool": "releases", "args": {"repo": "langchain-ai/langchain"}}, answer())
    second = stage2b_verify.searcher(budget=4, tools=tools(),
                                     confirm=lambda c, came_from, tools: verifier.confirm(c, came_from, tools, ask=ask))

    raised = stage2b_verify.verify_claim(claim(), [signal()], {"pypi_1": 1}, second=second)

    assert raised.evidence_kind == "registry_match" and raised.confidence == 0.8
    assert raised.evidence_found_by == "searched"
    assert raised.evidence_url.endswith("langchain-core%3D%3D1.4.2")


def test_a_claim_two_documents_already_support_is_never_sent_looking():
    asked = []
    second = stage2b_verify.searcher(budget=4, tools=tools(),
                                     confirm=lambda *args, **kw: asked.append(args))
    evidence = signal("gh_1", "github")

    already = stage2b_verify.verify_claim(claim(), [signal(), evidence], {"pypi_1": 1}, second=second)

    assert already.evidence_kind == "registry_match" and already.evidence_found_by == "collected"
    assert asked == []


def test_without_the_agent_a_lone_document_stays_a_lone_document():
    alone = stage2b_verify.verify_claim(claim(), [signal()], {"pypi_1": 1})

    assert alone.evidence_kind == "primary_report" and alone.confidence == 0.7
    assert alone.evidence_found_by == "collected"


def test_the_budget_is_what_stops_it():
    calls = []
    second = stage2b_verify.searcher(budget=2, tools=tools(),
                                     confirm=lambda c, came_from, tools: calls.append(c.version) or None)

    for _ in range(5):
        stage2b_verify.verify_claim(claim(), [signal()], {"pypi_1": 1}, second=second)

    assert len(calls) == 2


@pytest.mark.parametrize("reply", [["found"], "found", 7])
def test_a_reply_that_is_not_an_object_ends_it_without_a_crash(reply):
    assert verifier.confirm(claim(), "pypi", tools(), ask=scripted(reply)) is None
