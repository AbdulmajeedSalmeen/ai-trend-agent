from pathlib import Path
from src.schema import Score

def decide_action(score: Score) -> str:
    if score.confidence < 0.5:
        return "watch"

    if score.chapter_id is not None and score.priority >= 3.0:
        return "update_existing_material"

    if score.chapter_id is None and score.priority >= 2.5:
        return "add_new_lesson"

    return "watch"


def run(run_dir: Path) -> None:
    # TODO: decision table — see docs/plans/MEMBER-LEAD.md
    
    print("stage4_act: stub, not implemented yet")
