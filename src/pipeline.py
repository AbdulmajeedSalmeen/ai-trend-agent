import argparse
import time

from src import runio, trace
from src.adapters import model
from src.stages import stage1_ingest, stage2a_cluster, stage2b_verify, stage3_score, stage4_act

STAGES = [("ingest", stage1_ingest.run),
          ("cluster", stage2a_cluster.run),
          ("verify", stage2b_verify.run),
          ("score", stage3_score.run),
          ("act", stage4_act.run),
]
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None, help="replay a saved run instead of fetching")
    parser.add_argument("--budget", type=int, default=trace.DEFAULT_BUDGET,
                        help="token ceiling for the whole run; the model stops when it is spent")
    args = parser.parse_args()

    run_id = args.run_id or runio.new_run_id()
    run_path = runio.run_dir(run_id)
    model.reset()
    record = trace.start(run_id, model.describe(), budget=args.budget)

    stages = STAGES

    if args.run_id:
        stages = [(name, stage_run) for name, stage_run in STAGES if name != "ingest"]
        print(f"[{run_id}] replaying saved signals, ingest skipped")

    for name, stage_run in stages:
        trace.set_stage(name)
        print(f"[{run_id}] stage: {name}")
        started = time.perf_counter()
        stage_run(run_path)
        print(f"[{run_id}] stage {name} took {(time.perf_counter() - started) * 1000:.0f} ms")

    record.halted = model.halted()
    record.save(run_path)
    totals = record.summary()
    print(
        f"[{run_id}] {totals['calls']} model calls, {totals['tokens']} tokens, "
        f"${totals['cost_usd']:.4f}, {totals['failed_calls']} failed"
    )

    if record.halted:
        print(f"[{run_id}] model stopped early ({record.halted}); the stages used rules")

    if record.over_budget():
        print(f"[{run_id}] WARNING: token budget spent, later stages fell back to rules")

    print(f"[{run_id}] done")


if __name__ == "__main__":
    main()
