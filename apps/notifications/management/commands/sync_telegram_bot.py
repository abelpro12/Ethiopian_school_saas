import time
from django.core.management.base import BaseCommand
from apps.notifications.telegram_bot import TelegramBotHandler


class Command(BaseCommand):
    help = "Syncs Telegram Bot updates to link parents and handle incoming messages."

    def add_arguments(self, parser):
        parser.add_argument(
            '--poll',
            action='store_true',
            help='Continuously poll for incoming Telegram messages (daemon mode).',
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=3,
            help='Polling interval in seconds (default: 3s).',
        )

    def handle(self, *args, **options):
        is_poll = options.get('poll', False)
        interval = options.get('interval', 3)

        self.stdout.write(self.style.NOTICE("🤖 Checking Telegram Bot updates..."))
        token = TelegramBotHandler.get_token()
        if not token:
            self.stdout.write(self.style.ERROR("❌ No TELEGRAM_BOT_TOKEN found in settings or .env"))
            return

        if not is_poll:
            count = TelegramBotHandler.sync_updates()
            self.stdout.write(self.style.SUCCESS(f"✅ Processed {count} Telegram update(s)."))
            return

        self.stdout.write(self.style.SUCCESS(f"🚀 Telegram Bot poller started (Interval: {interval}s). Press Ctrl+C to stop."))
        try:
            while True:
                count = TelegramBotHandler.sync_updates()
                if count > 0:
                    self.stdout.write(self.style.SUCCESS(f"📥 Processed {count} incoming update(s)."))
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.NOTICE("\n🛑 Telegram Bot poller stopped."))
