"""The agent's reasons, in Arabic.

Every function here mirrors an English one and takes the same inputs, so the two
languages can differ in wording but never in facts: version strings, package and
API names, dates, counts and the priority are passed through exactly as they are.

The Arabic is built from rules, never from the model. Our checks on written
sentences look for English phrases, so an Arabic sentence written by a model
could not be held to the same standard. When the English reason on a card was
written by the model, the Arabic is the rules version of the same facts.

The words match the page's own labels, so a card never says one thing in its
chips and another in its sentence. Digits stay Latin, as on the rest of the page.
"""

from src import gap

# What a recurring pattern-table note says, in Arabic. A note not listed here is
# described in general terms rather than left in English mid-sentence.
NOTES = {
    "removed in langchain 1.x": "أُزيلت في langchain 1.x",
    "removed in langchain 1.x, replaced by create_retrieval_chain":
        "أُزيلت في langchain 1.x وحلّت محلها create_retrieval_chain",
    "removed in langchain 1.x, replaced by the LCEL pipe":
        "أُزيلت في langchain 1.x وحلّ محلها أنبوب LCEL",
    "removed in langchain 1.x, replaced by langgraph agents":
        "أُزيلت في langchain 1.x وحلّ محلها وكلاء langgraph",
    "most of it moved to langchain-classic in 1.x": "انتقل معظمها إلى langchain-classic في 1.x",
    "removed in openai 1.x": "أُزيلت في openai 1.x",
    "removed in langgraph 0.3": "أُزيلت في langgraph 0.3",
}
GENERIC_NOTE = "أُزيلت أو نُقلت في إصدار رئيسي لاحق"

# A pattern-table entry that describes a kind of call rather than naming one.
USES = {"langchain.chains imports": "استيرادات langchain.chains"}

# Counted nouns: the form for one, two, three to ten, and eleven to ninety-nine.
# Written as the subject of the sentence, so the one and two forms are in the
# nominative, and every other count takes the form Arabic fixes for it.
BREAKING = ("تغيير كاسر واحد", "تغييران كاسران", "تغييرات كاسرة", "تغييراً كاسراً")
FEATURE = ("ميزة جديدة واحدة", "ميزتان جديدتان", "ميزات جديدة", "ميزة جديدة")
FIX = ("إصلاح واحد", "إصلاحان", "إصلاحات", "إصلاحاً")
CHORE = ("مهمة صيانة واحدة", "مهمتا صيانة", "مهام صيانة", "مهمة صيانة")
JOB = ("وظيفة واحدة", "وظيفتان", "وظائف", "وظيفة")
VERSION = ("نسخة مؤكدة واحدة", "نسختان مؤكدتان", "نسخ مؤكدة", "نسخة مؤكدة")
# Months only ever follow آخر, so their one and two forms are the genitive.
MONTH = ("شهر", "شهرين", "أشهر", "شهراً")


def counted(n: int, forms: tuple[str, str, str, str]) -> str:
    """A number and its noun, agreeing the way Arabic requires."""
    one, two, few, many = forms

    if n == 1:
        return one

    if n == 2:
        return two

    tail = n % 100

    if 3 <= tail <= 10:
        return f"{n} {few}"

    if 11 <= tail <= 99:
        return f"{n} {many}"

    if n == 0:
        return f"0 {few}"

    # 100, 101, 102 and the like take the plain singular: the noun of "one"
    # without its "one".
    return f"{n} {one.rsplit(' ', 1)[0]}"


def listed(names: list[str]) -> str:
    return "، ".join(names)


def describe(subject: str, pinned: str | None, latest: str | None, kind: str,
             has_chapter: bool = True) -> str:
    """gap.describe."""
    if not has_chapter:
        if latest:
            return f"لا يثبّت أي فصل في المقرر {subject} ولا يدرّسه. أحدث إصدار مؤكد هو {latest}."
        return f"لا يثبّت أي فصل في المقرر {subject} ولا يدرّسه."

    if kind == gap.UNPINNED:
        if latest:
            return (f"تثبّت النوتبوكات {subject} بلا تحديد نسخة، فيحصل الطالب اليوم على {latest} "
                    f"أياً كانت النسخة التي كُتبت لها المادة.")
        return f"تثبّت النوتبوكات {subject} بلا تحديد نسخة."

    if kind == gap.DEPENDENCY:
        return (f"يثبّت الفصل {subject} بلا تحديد نسخة لكنه لا يدرّسه. "
                f"هذه اعتمادية تحتاج تثبيت نسختها، لا مادة تُعاد كتابتها.")

    if kind == gap.UNKNOWN:
        if latest:
            return f"نسخة {subject} التي يدرّسها الفصل غير مسجّلة، فلا يمكن قياس المسافة إلى {latest}."
        return f"لم يُؤكَّد أي إصدار من {subject} في هذه التشغيلة."

    if kind == gap.CURRENT:
        return f"يدرّس الفصل {subject} {pinned}، وهي أحدث نسخة مؤكدة."

    if kind == gap.AHEAD:
        return f"يدرّس الفصل {subject} {pinned}، ولم يُؤكَّد إصدار أحدث منها في هذه التشغيلة."

    if kind == gap.PATCH_ONLY:
        return f"انتقلت {subject} من {pinned} إلى {latest}: ترقيعات فقط، فالمادة ما زالت صالحة."

    if kind == gap.BEHIND_MINOR:
        return f"انتقلت {subject} من {pinned} إلى {latest}: قفزة صغرى، فقد لا يغطي الفصل سلوكاً جديداً."

    return f"انتقلت {subject} من {pinned} إلى {latest}: قفزة كبرى، فما يدرّسه الفصل قد يكون أُزيل."


def legacy_sentence(assessment: dict) -> str:
    """gap.legacy_sentence."""
    markers = assessment["legacy"]

    if not markers:
        return ""

    names = [USES.get(marker["uses"], marker["uses"]) for marker in markers[:4]]

    if len(names) == 1:
        note = NOTES.get(markers[0]["note"], GENERIC_NOTE)
        return f"لا تزال النوتبوكات تستدعي {names[0]}، ويقول جدول الأنماط لدينا إنها {note}."

    return (f"لا تزال النوتبوكات تستدعي {listed(names)}. وهي استدعاءات يصنّفها جدول الأنماط "
            f"لدينا بأنها أُزيلت أو نُقلت في إصدار رئيسي لاحق.")


def staleness_sentence(assessment: dict) -> str:
    """gap.staleness_sentence."""
    since = assessment["released_since"]
    updated = assessment["chapter_updated"]

    if not updated or since == 0:
        return ""

    return f"صدرت {counted(since, VERSION)} بعد آخر تحديث للفصل في {updated}."


def change_sentence(found: dict) -> str:
    """stage4_act.change_sentence. Release-note highlights are quotes and stay as written."""
    if not found:
        return ""

    highlights = [line.split(":", 1)[1].strip() for line in found.get("highlights", [])[:2]]
    named = f" ({'; '.join(highlights)})" if highlights else ""

    if found.get("breaking"):
        return f"في الإصدارات {counted(found['breaking'], BREAKING)}{named}."

    if found.get("deprecation"):
        return f"تعلن الإصدارات أن شيئاً صار مهجوراً{named}."

    if found.get("feature"):
        return f"في الإصدارات {counted(found['feature'], FEATURE)}{named}."

    return (f"الإصدارات صيانة فقط: {counted(found.get('fix', 0), FIX)} و"
            f"{counted(found.get('noise', 0), CHORE)}، لا جديد يُدرَّس.")


def market_sentence(found: dict, subject: str, installs: str | None, wanted: bool | None) -> str:
    """stage4_act.market_sentence. `installs` arrives already formatted, so the
    figure is the same characters in both languages."""
    jobs = found.get("jobs")

    if jobs is None and installs is None:
        return ""

    parts = []

    if jobs is not None:
        term = found.get("job_term") or subject
        months = counted(found.get("months", 3), MONTH)

        if jobs == 0:
            parts.append(f"لم تذكر أي وظيفة {term} في آخر {months}")
        else:
            # Two posts take the dual verb. Every other count takes the singular,
            # as a plural of things does.
            verb = "ذكرتا" if jobs == 2 else "ذكرت"
            parts.append(f"{counted(jobs, JOB)} {verb} {term} في آخر {months}")

    if installs is not None:
        parts.append(f"{installs} تثبيت الشهر الماضي")

    sentence = "، و".join(parts) + "."

    if wanted is False:
        sentence += " قلّة من أصحاب العمل يطلبونه حتى الآن."

    return sentence


def chapter_opening(chapter_id: str, teaches: str | None) -> str:
    return f"الفصل {chapter_id} يُدرّس: {teaches}" if teaches else ""


CLOSINGS = {
    "weak": "لم يُتخذ إجراء: الادعاءات أضعف من أن يُعتمد عليها.",
    "patch_only": "لا شيء يستدعي إعادة الكتابة بعد.",
    "unpinned": ("لا شيء مما قرأناه من إصداراتها يُظهر أنها تكسر ما يدرّسه الفصل أو تضيف ما يستحق "
                 "التدريس، فلا شيء يستدعي إعادة الكتابة. وتثبيت النسخة في النوتبوك يُبقي الأمر كذلك."),
    "behind_minor": ("يثبّت النوتبوك نسخته، فيعمل عند الطالب كما كُتب تماماً، ولا شيء مما قرأناه من "
                     "الإصدارات يُظهر أن الطريقة التي يدرّسها تغيّرت."),
    "not_wanted": "ليس درساً جديداً حتى يطلبه عدد أكبر من أصحاب العمل.",
}


def counts_line(confirmed: int, unverified: int, priority: float) -> str:
    return f"مؤكد: {confirmed}، غير مؤكد: {unverified}، الأولوية {priority:.2f}."


def fallback(subject: str, confirmed: int, unverified: int, priority: float,
             confidence: float, chapter_id: str | None) -> str:
    """The reason when there was no assessment to draw on."""
    where = f"الفصل {chapter_id}" if chapter_id else "لا يغطيه أي فصل"
    weak = " لم يُتخذ إجراء: الأدلة أضعف من اللازم." if confidence < 0.5 else ""

    return (f"{subject}: مؤكد {confirmed}، غير مؤكد {unverified}. "
            f"الأولوية {priority:.2f}، الثقة {confidence:.2f}، {where}.{weak}")
