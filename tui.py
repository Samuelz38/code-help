import os
from shutil import disk_usage
from pathlib import Path

from dotenv import load_dotenv
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, ProgressBar

from components_for_tui import ServiceMonitor

load_dotenv()

PATH_ROOT = Path(__file__).parent.resolve()
LOGS_DIR = PATH_ROOT / 'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'codehelper')
DB_USER = os.getenv('DB_USER', 'codehelper')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'codehelper123')

SERVICE_PORTS = [
    ('PostgreSQL', DB_HOST, int(DB_PORT) if DB_PORT.isdigit() else 5432),
    ('Grafana', os.getenv('GRAFANA_HOST', 'localhost'), int(os.getenv('GRAFANA_PORT', '3000'))),
    ('Prometheus', os.getenv('PROMETHEUS_HOST', 'localhost'), int(os.getenv('PROMETHEUS_PORT', '9090'))),
    ('Loki', os.getenv('LOKI_HOST', 'localhost'), int(os.getenv('LOKI_PORT', '3100'))),
]


class MyApp(App):
    TITLE = 'Code Help - Configuração'
    CSS_PATH = str(PATH_ROOT / 'style.css')
    BINDINGS = [
        Binding('escape', 'quit', 'Sair'),
        Binding('tab', 'focus_next', 'Próximo campo'),
        Binding('shift+tab', 'focus_previous', 'Campo anterior'),
    ]

    def compose(self) -> ComposeResult:
        usage = disk_usage(PATH_ROOT)
        used_gb = usage.used / 1024**3
        free_gb = usage.free / 1024**3

        yield Header(show_clock=True)

        with Container(classes='main'):
            with Vertical(classes='config-panel'):
                yield Label('CONFIGURAÇÃO DO BANCO DE DADOS', classes='section-title')
                yield Input(value=DB_HOST, placeholder='localhost', id='db_host')
                yield Input(value=DB_PORT, placeholder='5432', id='db_port')
                yield Input(value=DB_NAME, placeholder='codehelper', id='db_name')
                yield Input(value=DB_USER, placeholder='codehelper', id='db_user')
                yield Input(value=DB_PASSWORD, placeholder='senha', id='db_password', password=True)
                yield Button('Salvar configurações', id='button_save', classes='button_save')
                yield Label(
                    'Use TAB para navegar, SHIFT+TAB para voltar e ENTER para salvar.',
                    classes='hint-label',
                )
                yield Label('', id='save_message', classes='status-message')

            with Vertical(classes='status-panel'):
                yield Label('STATUS DO SISTEMA', classes='section-title')
                yield Label(
                    f'Disco usado: {used_gb:.2f} GB / Disponível: {free_gb:.2f} GB',
                    id='disk_summary',
                )
                disk_bar = ProgressBar(total=usage.total, id='disk_bar')
                disk_bar.update(progress=usage.used)
                yield disk_bar
                yield Label('SERVIÇOS', classes='section-subtitle')
                for name, host, port in SERVICE_PORTS:
                    yield ServiceMonitor(name, host, port, classes='service-block')
                yield Label('Apenas configurações e monitoramento básico.', classes='hint-label')

        yield Footer()

    async def update_system_stats(self) -> None:
        try:
            usage = disk_usage(PATH_ROOT)
            used_gb = usage.used / 1024**3
            free_gb = usage.free / 1024**3
            self.query_one('#disk_summary', Label).update(
                f'Disco usado: {used_gb:.2f} GB / Disponível: {free_gb:.2f} GB'
            )
            self.query_one('#disk_bar', ProgressBar).update(
                progress=usage.used, total=usage.total
            )
        except Exception as exc:
            self.query_one('#save_message', Label).update(f'[red]Erro ao atualizar disco: {exc}')

    def on_mount(self) -> None:
        self.set_interval(3.0, self.update_system_stats)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == 'button_save':
            self.save_database_config()

    def save_database_config(self) -> None:
        host = self.query_one('#db_host', Input).value.strip()
        port = self.query_one('#db_port', Input).value.strip()
        name = self.query_one('#db_name', Input).value.strip()
        user = self.query_one('#db_user', Input).value.strip()
        password = self.query_one('#db_password', Input).value.strip()

        message = self.query_one('#save_message', Label)

        if not host or not port or not name or not user:
            message.update('[red]Preencha todos os campos antes de salvar.')
            return

        if not port.isdigit():
            message.update('[red]A porta precisa ser um número válido.')
            return

        env_path = PATH_ROOT / '.env'
        env_content = (
            f'DB_HOST={host}\n'
            f'DB_PORT={port}\n'
            f'DB_NAME={name}\n'
            f'DB_USER={user}\n'
            f'DB_PASSWORD={password}\n'
        )

        try:
            env_path.write_text(env_content, encoding='utf-8')
            message.update('[green]Configurações salvas em .env')
        except Exception as exc:
            message.update(f'[red]Falha ao salvar .env: {exc}')


if __name__ == '__main__':
    MyApp().run()
