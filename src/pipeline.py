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
    run_id = runio.new_run_id()
    run_path = runio.run_dir(run_id)

    for name, stage_run in STAGES:
        print(f"[{run_id}] stage: {name}")

        stage_run(run_path)

    print(f"[{run_id}] done")
if __name__ == "__main__":
    main()
