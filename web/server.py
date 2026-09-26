import re
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

from src import runio
from web import runner, site

app = FastAPI(title="AI Trend Agent")

ICON_RE = re.compile(r'<link rel="icon" type="image/svg\+xml" href="data:image/svg\+xml,([^"]+)"')


class RunRequest(BaseModel):
    replay_run_id: str | None = None


def page() -> str:
    """The page with no run in it: the browser asks the API for one. The material
    review goes in when this machine has one, since a served page is never committed."""
    return site.page_html("null", site.material_json())


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return page()


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """The icon the page declares, for tabs that ask the server rather than the
    page: the Claude app's browser pane, and a browser opening /api/* directly.
    Read from the template, so the design stays in one place."""
    found = ICON_RE.search(site.TEMPLATE_PATH.read_text(encoding="utf-8"))

    if found is None:
        return Response(status_code=204)

    return Response(unquote(found.group(1)), media_type="image/svg+xml")


@app.get("/api/runs")
def runs() -> JSONResponse:
    return JSONResponse({"runs": runner.list_runs()})


@app.get("/api/run/{run_id}")
def run_payload(run_id: str) -> JSONResponse:
    run_dir = runio.RUNS_DIR / run_id
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="run not found")
    return JSONResponse(site.build_payload(run_dir))

@app.get("/api/latest")
def latest() -> JSONResponse:
    complete = [r for r in runner.list_runs() if r["complete"]]
    if not complete:
        raise HTTPException(status_code=404, detail="no complete run yet")
    return JSONResponse(site.build_payload(runio.RUNS_DIR / complete[0]["run_id"]))


@app.get("/api/status")
def run_status() -> JSONResponse:
    return JSONResponse(runner.status())


@app.post("/api/run")
def start_run(request: RunRequest) -> JSONResponse:
    result = runner.start(request.replay_run_id)
    return JSONResponse(result, status_code=202 if result["ok"] else 409)


@app.get("/api/budget")
def budget() -> JSONResponse:
    try:
        return JSONResponse({"remaining": runner.github_budget()})
    except Exception as error:
        return JSONResponse({"remaining": None, "error": str(error)})


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8800)


if __name__ == "__main__":
    main()
