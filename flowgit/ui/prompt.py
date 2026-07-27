from rich.prompt import Prompt

def ask_username():
    username = Prompt.ask(
        "Enter username"
    )
    return username

def ask_email():
    email = Prompt.ask(
        "Enter email"
    )
    return email