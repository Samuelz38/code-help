from datetime import datetime

from textual.widgets import Static

from src.utils.verify_functions import check_service


class ServiceMonitor(Static):
    def __init__(self, name: str, host: str, port: int, **kwargs):
        super().__init__(**kwargs)
        self.service_name = name
        self.host = host or 'localhost'
        self.port = int(port) if port else 0

    def on_mount(self):
        self.set_interval(5, self.update_status)
        self.call_later(self.update_status)

    async def update_status(self):
        if self.port <= 0:
            status_text = '[yellow]Porta inválida[/]'
        else:
            is_up = await check_service(self.host, self.port)
            status_text = '[green]ON[/]' if is_up else '[red]OFF[/]'

        now = datetime.now().strftime('%H:%M:%S')
        self.update(
            f'[b]{self.service_name}[/b]\n'
            f'Host: {self.host}:{self.port}\n'
            f'Status: {status_text}\n'
            f'Última verificação: {now}'
        )

