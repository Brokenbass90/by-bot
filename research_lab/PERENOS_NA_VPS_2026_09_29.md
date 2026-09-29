# Перенос исследования на VPS: 24/7 вместо «пока включён ноутбук»

29 сентября 2026. Переезжают ТРИ долгоживущих процесса без денег и ключей:
ядро ETS2M, тень SILA, демон фабрики вместе с суточным циклом Polymarket.

## Зачем

За неделю 25–28 сентября Mac не работал трое суток из семи. ETS2M дал
1 вход 25-го, ноль 26-го и 27-го; тень SILA от выключения умерла и потеряла
двое суток решений. Всё, что копится проспективно, копится только пока
машина включена. На VPS этой зависимости нет.

Это НЕ ускоряет вычисления. Это увеличивает количество накопленных
проспективных данных примерно вдвое — ровно на долю простоя.

## Что НЕ делаем

- не трогаем продакшн Codex: он в `/root/by-bot`, мы ставим себя
  в `/root/research-24x7/by-bot`, отдельный каталог, отдельные логи и замки;
- не везём ключи, конфиги, `.env`, `signal_copy`: список переносимого
  БЕЛЫЙ, по именам, туда нечему попасть случайно;
- не начинаем ничего заново: ни новой эпохи ETS2M, ни нового старта тени,
  ни чистого реестра;
- не меняем ни одной стратегии, ни одного порога, ни одной предрегистрации.

## Что везём и чем

    код, реестр, очередь, вердикты, вселенные   →  git, ветка research/fabrika-v1
    состояние, которого в git нет               →  rsync, белый список

Белый список (скрипт `perenos_na_vps.sh`), всего около 130 МБ:

    research_lab/data/yadro/                    1.2 МБ   когорта ETS2M
    research_lab/data/ten_SILA.jsonl            8 КБ     решения тени
    research_lab/data/ten_SILA_sostoyanie.json  4 КБ     ЗАМОРОЖЕННЫЙ старт
    research_lab/data/ten_SILA_ceny.json        1.1 МБ   кэш цен
    research_lab/data/poly/istoriya/            47 МБ    4928 рынков
    research_lab/data/poly/otobrano.json        2.1 МБ   сопоставление
    research_lab/data/pit_daily/                78 МБ    дневные цены крипты

Каталог Polymarket на 5.7 ГБ НЕ везём: он нужен только чтобы заново собрать
сопоставление, а оно уже собрано и едет готовым.

## Порядок. Шаги 1–4 ничего не ломают, откат бесплатный.

**1. Сухой прогон на Mac.** Ничего не отправляет, только показывает список.

    bash research_lab/perenos_na_vps.sh --proverka

**2. Снять эталонные числа НА MAC, прямо перед переносом.** Это точка,
с которой потом сверяем VPS. Запишите вывод.

    python3 - <<'PY'
    import json, os
    n = lambda p: sum(1 for _ in open(p, encoding="utf-8", errors="ignore")) if os.path.exists(p) else None
    print("ETS2M входов      :", n("research_lab/data/yadro/ETS2M/vhody.jsonl"))
    print("ETS2M исходов     :", n("research_lab/data/yadro/ETS2M/ishody.jsonl"))
    print("SILA решений      :", n("research_lab/data/ten_SILA.jsonl"))
    print("SILA старт        :", json.load(open("research_lab/data/ten_SILA_sostoyanie.json"))["nachalo"])
    print("фабрика вердиктов :", n("research_lab/fabrika/verdikty.jsonl"))
    print("фабрика пунктов   :", len(json.load(open("research_lab/fabrika/ochered.json"))["ochered"]))
    PY

На 29.09 16:40 UTC было: входов 972, исходов 2719, решений тени 2,
старт тени 2026-09-24T07:01:24+00:00, вердиктов 113, пунктов 116.

**3. Код на VPS — отдельным клоном, продакшн не трогаем.**

    ssh root@64.226.73.119
    mkdir -p /root/research-24x7 && cd /root/research-24x7
    git clone -b research/fabrika-v1 git@github.com:Brokenbass90/by-bot.git
    cd by-bot && python3 -m venv .venv-research
    .venv-research/bin/pip install numpy

**4. Состояние на VPS.** С Mac:

    bash research_lab/perenos_na_vps.sh --vezti

**5. Проверка ДО запуска.** На VPS:

    cd /root/research-24x7/by-bot && bash research_lab/vps_proverka.sh

Числа обязаны совпасть с шагом 2. Момент старта тени обязан быть тем же
самым — если он другой, тень начнёт отсчёт заново и потеряет проспективность.
Не совпало — остановиться и разобраться, не запускать.

**6. Запуск.** На VPS:

    bash research_lab/vps_zapusk.sh
    bash research_lab/vps_proverka.sh

Писателей должно быть ровно по одному на процесс.

**7. Доказательство перезапуска.** На VPS: записать числа, убить всё,
поднять заново, сверить.

    pkill -f "yadro.py --epoha ETS2M"; pkill -f ten_sila.py; pkill -f "fabrika.py --demon"
    sleep 3 && bash research_lab/vps_zapusk.sh && bash research_lab/vps_proverka.sh

Счётчики обязаны продолжиться, а не обнулиться; дублей быть не должно.

**8. И только теперь гасим копии на Mac.** Пока этот шаг не сделан,
пишут двое, и журналы разъедутся.

    pkill -f "yadro.py --epoha ETS2M"
    pkill -f ten_sila.py
    pkill -f "fabrika.py --demon"
    echo "перенесено на VPS $(date -u)" > research_lab/data/PERENESENO_NA_VPS.txt

Тени ETS2S и ATT1 остаются на Mac: они принадлежат другому контуру,
их переносом занимается Codex, если сочтёт нужным.

## Что после переноса меняется для владельца

Ноутбук можно выключать. ETS2M доведёт 151 позицию WIDE, тень SILA будет
принимать решение каждые сутки, Polymarket собираться, фабрика держать
очередь. Я замолчу до события: терминальность WIDE → вердикт ETS2M.

## Что НЕ меняется

Потолок автоматизации прежний — READY_FOR_BUILD. Ни один из трёх процессов
не умеет торговать и не имеет доступа к брокеру. Деньги и LIVE — Codex
и ваше письменное решение, и переезд на сервер этого не касается.
