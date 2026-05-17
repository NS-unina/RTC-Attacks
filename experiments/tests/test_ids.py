import typer

from experiments.infra.ids import IdsController

# Inizializziamo l'app Typer
app = typer.Typer(help="Test Makefile-based lab execution")



@app.command()
def start():
    print("Starting IDS...")
    ids = IdsController()
    ids.start()

@app.command() 
def stop():
    print("Stopping IDS...")
    ids = IdsController()
    ids.stop()


if __name__ == "__main__":
    app()