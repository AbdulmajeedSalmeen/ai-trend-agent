import argparse

from src import runio
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
    args = parser.parse_args()

    run_id = args.run_id or runio.new_run_id()
    run_path = runio.run_dir(run_id)

    stages = STAGES

    if args.run_id:
        stages = [(name, stage_run) for name, stage_run in STAGES if name != "ingest"]
        print(f"[{run_id}] replaying saved signals, ingest skipped")

    for name, stage_run in stages:
        print(f"[{run_id}] stage: {name}")
        stage_run(run_path)

    print(f"[{run_id}] done")


if __name__ == "__main__":
    main()
