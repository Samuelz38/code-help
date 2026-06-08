import os
from shutil import disk_usage
from pathlib import Path

from dotenv import load_dotenv
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, ScrollableContainer, Vertical
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
HF_TOKEN = os.getenv('HF_TOKEN', '')
REPO_PATH = os.getenv('REPO_PATH', './projects/coloque seu projeto aqui')
PROJECT_NAME = os.getenv('PROJECT_NAME', 'coloque seu o nome do seu projeto aqui')

CONFIG_FIELDS = [
    ('DB_HOST', DB_HOST, 'localhost', False),
    ('DB_PORT', DB_PORT, '5432', False),
    ('DB_NAME', DB_NAME, 'codehelper', False),
    ('DB_USER', DB_USER, 'codehelper', False),
    ('DB_PASSWORD', DB_PASSWORD, 'senha', True),
    ('HF_TOKEN', HF_TOKEN, 'Preencha com seu token', True),
    ('REPO_PATH', REPO_PATH, 'Caminho para o repositório', False),
    ('PROJECT_NAME', PROJECT_NAME, 'Nome do projeto', False),
    ('GRAFANA_HOST', os.getenv('GRAFANA_HOST', 'localhost'), 'localhost', False),
    ('GRAFANA_PORT', os.getenv('GRAFANA_PORT', '3000'), '3000', False),
    ('PROMETHEUS_HOST', os.getenv('PROMETHEUS_HOST', 'localhost'), 'localhost', False),
    ('PROMETHEUS_PORT', os.getenv('PROMETHEUS_PORT', '9090'), '9090', False),
    ('LOKI_HOST', os.getenv('LOKI_HOST', 'localhost'), 'localhost', False),
    ('LOKI_PORT', os.getenv('LOKI_PORT', '3100'), '3100', False),
]

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
            with ScrollableContainer(classes='config-panel'):
                yield Label('CONFIGURAÇÃO DO SISTEMA', classes='section-title')
                for name, value, placeholder, password in CONFIG_FIELDS:
                    yield Label(name.replace('_', ' '), classes='input-label')
                    yield Input(
                        value=value,
                        placeholder=placeholder,
                        id=name.lower(),
                        password=password,
                    )
                yield Button('Salvar configurações', id='button_save', classes='button_save')
                yield Label(
                    'Use TAB para navegar, SHIFT+TAB para voltar e ENTER para salvar.',
                    classes='hint-label',
                )
                yield Label('', id='save_message', classes='status-message')

            with ScrollableContainer(classes='status-panel'):
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
        message = self.query_one('#save_message', Label)

        values = {}
        for name, _, _, password in CONFIG_FIELDS:
            value = self.query_one(f'#{name.lower()}', Input).value.strip()
            values[name] = value

        required_fields = ['DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER']
        for field in required_fields:
            if not values.get(field):
                message.update('[red]Preencha todos os campos obrigatórios antes de salvar.')
                return

        if not values['DB_PORT'].isdigit():
            message.update('[red]A porta do banco precisa ser um número válido.')
            return

        optional_ports = ['GRAFANA_PORT', 'PROMETHEUS_PORT', 'LOKI_PORT']
        for field in optional_ports:
            if values.get(field) and not values[field].isdigit():
                message.update(f'[red]A porta {field} precisa ser um número válido.')
                return

        env_path = PATH_ROOT / '.env'
        env_lines = []
        for name, _, _, _ in CONFIG_FIELDS:
            env_lines.append(f'{name}={values.get(name, "")}')
        env_content = '\n'.join(env_lines) + '\n'

        try:
            env_path.write_text(env_content, encoding='utf-8')
            message.update('[green]Configurações salvas em .env')
        except Exception as exc:
            message.update(f'[red]Falha ao salvar .env: {exc}')


if __name__ == '__main__':
    MyApp().run()
