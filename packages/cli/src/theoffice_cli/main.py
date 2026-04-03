import typer

cli = typer.Typer(help="theoffice CLI", no_args_is_help=True)


@cli.callback()
def _root() -> None:
    """theoffice command group."""


@cli.command()
def version() -> None:
    """Print CLI version."""
    typer.echo("theoffice-cli 0.1.0")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
