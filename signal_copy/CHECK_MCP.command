#!/bin/bash
# Проверка: доступен ли MCP-сервер MetaTrader 5 из macOS.
# Запусти двойным кликом ИЛИ в Терминале: bash CHECK_MCP.command
echo "── Слушает ли кто-то порт 22346 ──"
lsof -nP -iTCP:22346 -sTCP:LISTEN 2>/dev/null || echo "  (lsof ничего не нашёл)"
echo
echo "── Отвечает ли порт ──"
nc -z -G 2 127.0.0.1 22346 && echo "  ПОРТ ОТКРЫТ ✅" || echo "  порт закрыт ❌"
echo
echo "── Что отдаёт по HTTP ──"
curl -s -i -m 5 http://127.0.0.1:22346/mcp | head -20
echo
curl -s -i -m 5 http://127.0.0.1:22346/sse | head -10
echo
echo "── Готово. Пришли весь вывод целиком. ──"
read -p "Нажми Enter чтобы закрыть"
