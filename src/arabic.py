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
# Nouns the action plan counts after a preposition as well as before a verb, so
# they carry a fifth form: the dual as a preposition leaves it.
LINE = ("سطر استيراد واحد", "سطرا استيراد", "أسطر استيراد", "سطر استيراد", "سطرَي استيراد")
NOTEBOOK = ("نوتبوك واحد", "نوتبوكان", "نوتبوكات", "نوتبوكاً", "نوتبوكين")
CHAPTER = ("فصل واحد", "فصلان", "فصول", "فصلاً", "فصلين")


def counted(n: int, forms: tuple[str, ...], oblique: bool = False) -> str:
    """A number and its noun, agreeing the way Arabic requires. `oblique` is for a
    count that follows a preposition, where only the dual changes its ending."""
    one, two, few, many = forms[:4]

    if n == 1:
        return one

    if n == 2:
        return forms[4] if oblique and len(forms) > 4 else two

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
    verified = [marker for marker in assessment["legacy"] if marker.get("verified")]
    typed = [marker for marker in assessment["legacy"] if not marker.get("verified")]

    return " ".join(part for part in (verified_sentence(verified), typed_sentence(typed)) if part)


def verified_sentence(markers: list[dict]) -> str:
    """gap.verified_sentence."""
    if not markers:
        return ""

    names = [marker["uses"] for marker in markers[:4]]

    if len(names) == 1:
        return (f"لا تزال النوتبوكات تستورد {names[0]} من مسار لم يعد في {markers[0]['checked']}، "
                f"وهي الآن من {markers[0]['module']}.")

    return (f"لا تزال النوتبوكات تستورد {listed(names)} من مسارات لم تعد في {markers[0]['checked']}، "
            f"وقائمة التعديلات تبيّن أين انتقل كل منها.")


def typed_sentence(markers: list[dict]) -> str:
    """gap.typed_sentence."""
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
    "optional": "يستحق مادة اختيارية، لا درساً أساسياً، حتى يطلبه عدد أكبر من أصحاب العمل.",
    "course_wide": "الإصدار نفسه يتجاوز هذا الفصل: خطّط للانتقال مرة واحدة للمقرر كله.",
}


def spread_sentence(subject: str, latest: str, notebooks: int, chapters: int) -> str:
    """stage4_act.spread_sentence."""
    return (f"على مستوى المقرر، أسماء لم تعد في {subject} {latest} يستوردها "
            f"{counted(notebooks, NOTEBOOK)} في {counted(chapters, CHAPTER, oblique=True)}.")


def demand(facts: dict, installs: str | None) -> str:
    parts = []

    if facts.get("jobs") is not None:
        parts.append(f"{counted(facts['jobs'], JOB)} في آخر {counted(facts['months'], MONTH)}")

    if installs is not None and facts.get("installs") is not None:
        parts.append(f"{installs} تثبيت الشهر الماضي")

    return "، و".join(parts)


def asked(facts: dict) -> str:
    months = counted(facts["months"], MONTH)

    if facts["jobs"] == 0:
        return f"فلم تذكره أي وظيفة في آخر {months}"

    return f"فقد ذكرته {counted(facts['jobs'], JOB)} في آخر {months}"


def stable_step(key: str, facts: dict) -> str:
    """plan.english_stable."""
    beta = f"فـ{facts['latest']} إصدار تجريبي"

    if key in ("pin", "pin_guard", "pin_dependency"):
        return f"ثبّت {facts['subject']} على أحدث إصدار مستقر في خلية التثبيت، {beta}."

    if key in ("bump", "bump_minor"):
        return f"انقل التثبيت من {facts['subject']} {facts['pinned']} إلى أحدث إصدار مستقر، {beta}."

    return (f"شغّل نوتبوكات {facts['chapter']} على أحدث إصدار مستقر من {facts['subject']} "
            f"قبل الدفعة القادمة، {beta}.")


def plan_step(key: str, facts: dict, installs: str | None = None) -> str:
    """plan.english, step for step. `installs` arrives formatted, as in market_sentence."""
    if facts.get("prerelease"):
        return stable_step(key, facts)

    if key == "fix_now":
        return (f"أصلح أولاً ما يتعطل عند التثبيت اليوم: {counted(facts['lines'], LINE)} في "
                f"{counted(facts['notebooks'], NOTEBOOK, oblique=True)} ({listed(facts['chapters'])}).")

    if key == "decide_line":
        return (f"قرّر مرة واحدة للمقرر كله: البقاء على خط {facts['subject']} الذي يثبّته "
                f"{counted(facts['notebooks'], NOTEBOOK)} ({listed(facts['specs'])})، "
                f"أو الانتقال إلى {facts['subject']} {facts['latest']}.")

    if key == "move_lines":
        return (f"للانتقال: تغيير {counted(facts['lines'], LINE, oblique=True)} في "
                f"{counted(facts['notebooks'], NOTEBOOK, oblique=True)} من "
                f"{counted(facts['chapters'], CHAPTER, oblique=True)}، وقائمة التعديلات تسمّي كل خلية.")

    if key == "change_lines":
        return (f"غيّر في {facts['chapter']}: {counted(facts['lines'], LINE)} في "
                f"{counted(facts['notebooks'], NOTEBOOK, oblique=True)}، وقائمة التعديلات تسمّي كل خلية.")

    if key == "legacy":
        return f"استبدل الاستدعاءات التي أزالها الإصدار: {listed(facts['uses'])}."

    if key == "pin":
        return f"ثبّت {facts['subject']}=={facts['latest']} في خلية التثبيت، ليعمل النوتبوك كما كُتب."

    if key == "bump":
        return (f"انقل التثبيت من {facts['subject']} {facts['pinned']} إلى {facts['latest']}، "
                f"ثم أصلح ما غيّره الإصدار الرئيسي.")

    if key == "bump_minor":
        return f"انقل التثبيت من {facts['subject']} {facts['pinned']} إلى {facts['latest']}."

    if key == "breaking":
        return f"راجع الدرس مقابل هذا التغيير الكاسر: {facts['highlight']}."

    if key == "deprecation":
        return f"استبدل ما صار مهجوراً في الإصدار: {facts['highlight']}."

    if key == "feature":
        return f"فكّر في قسم قصير عن الجديد: {facts['highlight']}."

    if key == "rerun":
        return f"شغّل نوتبوكات {facts['chapter']} على {facts['subject']} {facts['latest']} قبل الدفعة القادمة."

    if key == "outline":
        found = demand(facts, installs)
        return f"ضع مخططاً لدرس عن {facts['subject']}: {found}." if found else \
            f"ضع مخططاً لدرس عن {facts['subject']} ومكانه في المقرر."

    if key == "optional":
        return f"أضف نوتبوكاً اختيارياً عن {facts['subject']}، خارج المسار الأساسي."

    if key == "build_on":
        return f"ابنِ النوتبوك حول ما يضيفه {facts['latest']}: {facts['highlight']}."

    if key == "review":
        return "اعرضه على المدرّب للمراجعة قبل الدفعة القادمة."

    if key == "promote":
        wanted = "أصحاب العمل" if facts["jobs"] == 0 else "عدد أكبر من أصحاب العمل"
        return f"حوّله إلى درس حين يطلبه {wanted}، {asked(facts)}."

    if key == "wait_confirm":
        return "انتظر إصداراً رسمياً يؤكد الادعاءات قبل أي إجراء."

    if key == "recheck_notes":
        return f"اقرأ ملاحظات إصدار {facts['subject']} القادم قبل الدفعة القادمة."

    if key == "nothing_new":
        return "لا شيء يُضاف: الإصدارات إصلاح وصيانة فقط."

    if key == "revisit_market":
        wanted = "أصحاب العمل" if facts["jobs"] == 0 else "عدد أكبر من أصحاب العمل"
        return f"أعد النظر حين يطلبه {wanted}، {asked(facts)}."

    if key == "leave_patch":
        return "اترك الفصل كما هو: ما صدر بعد نسخته ترقيعات فقط."

    if key == "recheck_minor":
        return f"أعد الفحص حين يصدر {facts['subject']} إصداراً صغيراً أو كبيراً بعد {facts['latest']}."

    if key == "pin_guard":
        return f"ثبّت {facts['subject']}=={facts['latest']} في خلية التثبيت، حتى لا يغيّر الإصدار القادم الدرس."

    if key == "pin_dependency":
        return f"ثبّت {facts['subject']}=={facts['latest']} في خلية التثبيت، والدرس نفسه لا يحتاج تغييراً."

    if key == "leave_dependency":
        return "اترك الدرس كما هو: الفصل يثبّتها ولا يدرّسها."

    if key == "leave_pinned":
        return f"اترك الفصل كما هو: النوتبوك يثبّت {facts['pinned']} ويعمل كما كُتب."

    if key == "recheck_major":
        return f"أعد الفحص حين يصدر {facts['subject']} إصداراً رئيسياً."

    if key == "leave_current":
        return "اترك الفصل كما هو: يدرّس أحدث إصدار مؤكد."

    if key == "record_version":
        return f"سجّل نسخة {facts['subject']} التي يستخدمها الفصل، ليقيس التشغيل القادم المسافة."

    raise KeyError(key)


def counts_line(confirmed: int, unverified: int, priority: float) -> str:
    return f"مؤكد: {confirmed}، غير مؤكد: {unverified}، الأولوية {priority:.2f}."


def fallback(subject: str, confirmed: int, unverified: int, priority: float,
             confidence: float, chapter_id: str | None) -> str:
    """The reason when there was no assessment to draw on."""
    where = f"الفصل {chapter_id}" if chapter_id else "لا يغطيه أي فصل"
    weak = " لم يُتخذ إجراء: الأدلة أضعف من اللازم." if confidence < 0.5 else ""

    return (f"{subject}: مؤكد {confirmed}، غير مؤكد {unverified}. "
            f"الأولوية {priority:.2f}، الثقة {confidence:.2f}، {where}.{weak}")
