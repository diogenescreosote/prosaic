"""Command-line entry points.

Everything here is a thin shell over the library: the deadline command
calls the engine, the forms command reads the pack, and ask runs the
operator against a matter file. The CLI never computes anything itself.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Annotated

import typer

from prosaic.agent import Operator
from prosaic.agent.operator import MessageCreator
from prosaic.agent.toolkit import DeadlineRuleName, run_rule
from prosaic.deadlines import ServiceMethod, california_court_calendar
from prosaic.model import Matter
from prosaic.packs.civil import CIVIL_PACK

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def deadline(
    rule: DeadlineRuleName,
    trigger: Annotated[
        datetime.datetime,
        typer.Argument(formats=["%Y-%m-%d"], help="The rule's trigger date, e.g. 2026-10-02"),
    ],
    method: Annotated[
        ServiceMethod,
        typer.Option(help="Service method, where the rule has extensions"),
    ] = ServiceMethod.PERSONAL,
) -> None:
    """Compute one statutory deadline."""
    try:
        result = run_rule(rule, trigger.date(), method, california_court_calendar())
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"{result.date.isoformat()}  {result.citation}")
    typer.echo(result.description)


@app.command()
def forms() -> None:
    """List the forms the civil pack can fill."""
    for form in CIVIL_PACK.forms:
        typer.echo(f"{form.number}  {form.title}")


@app.command()
def holidays(year: int) -> None:
    """List the court holidays of one covered year."""
    calendar = california_court_calendar()
    matching = sorted(day for day in calendar.holidays if day.year == year)
    if not matching:
        typer.echo(
            f"no holiday data for {year}; coverage is {calendar.first_day} to {calendar.last_day}",
            err=True,
        )
        raise typer.Exit(code=1)
    for day in matching:
        typer.echo(day.isoformat())


@app.command()
def ask(
    matter_file: Annotated[Path, typer.Argument(help="A Matter serialized as JSON")],
    question: str,
) -> None:
    """Ask the operator a question about a matter. Needs ANTHROPIC_API_KEY."""
    matter = Matter.model_validate_json(matter_file.read_text())
    operator = Operator(_anthropic_client(), matter, california_court_calendar(), CIVIL_PACK)
    typer.echo(operator.ask(question))


def _anthropic_client() -> MessageCreator:
    import anthropic

    return anthropic.Anthropic().messages


if __name__ == "__main__":
    app()
