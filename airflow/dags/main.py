
import random
from collections import deque
from playwright.sync_api import sync_playwright
import time
import requests
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable, DagModel
from airflow.utils.session import create_session
from datetime import datetime, timedelta
import random
from collections import deque
from playwright.sync_api import sync_playwright


from logger_module import setup_logging
# Настройка логгера
logger = setup_logging(
    logger_name="link_ticketer",
    log_file="link_ticketer.log")
link = 'https://tce.by/shows.html?base=QzVDQkNGM0ItQ0U5OC00OUEzLTk2RkUtQkIxRTAyRTczQkI2&data=8156'
NUMBER_OF_SEATS = 3


def send_telegram_notification(message):
    token = Variable.get("tg_token")
    chat_id = Variable.get("tg_chat_id")
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    # Используем HTML вместо Markdown, он менее капризный к спецсимволам
    data = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}

    try:
        response = requests.post(url, json=data)
        # Это вызовет исключение, если статус-код не 200
        response.raise_for_status()

        logger.info(f"Telegram notification sent successfully")
    except requests.exceptions.HTTPError as e:
        # Здесь мы увидим ответ от серверов Telegram (например, "Bad Request: can't parse entities")
        logger.error(f"Telegram API Error: {response.text}")
    except Exception as e:
        logger.error(f"General Error sending telegram notification: {e}")

# --- ФУНКЦИЯ ПАУЗЫ DAG ---


def pause_self(dag_id):
    with create_session() as session:
        dag_model = session.query(DagModel).filter(
            DagModel.dag_id == dag_id).first()
        if dag_model:
            dag_model.is_paused = True
            session.commit()
            logger.warning(
                f"DAG {dag_id} поставлен на паузу, так как билеты куплены.")


def open_page_via_link() -> bool:
    '''
    Функция для открытия страницы через ссылку и бронирования билетов
    Args:
        link: str - ссылка на страницу с билетами
        number_of_seats: int - количество билетов для бронирования
    Returns:
        bool: True если билеты успешно забронированы, False в противном случае
    '''
    try:
        # Получаем креды из Airflow
        login = Variable.get("ticket_login")
        password = Variable.get("ticket_password")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            # сперва аутентифицируемся <li id="user_menu" class="last">
            auth_link = 'https://tce.by/users.html'
            page = browser.new_page()

            page.goto(auth_link, timeout=10000,)
            time.sleep(2)
            box = page.locator("#user_menu").bounding_box()
            if box:
                page.mouse.click(box['x'] + box['width'] / 2,
                                 box['y'] + box['height'] / 2)
                time.sleep(1)
            else:
                logger.info("Element user_menu not found")
                return False
            # находим элемент <li id="user_menu" class="last">
            page.locator('input[name="login"]').wait_for(state="visible")

            # Теперь можно заполнять форму
            page.locator('input[name="login"]').fill(login)
            page.locator('input[name="pass"]').fill(password)

            # Клик по ссылке "Войти" (которая вызывает JS функцию loginUser)
            page.get_by_role("link", name="Войти").click()
            time.sleep(2)
            page.goto(link, timeout=10000)
            time.sleep(2)
            # находим элементы <td, где есть атрибут data-cost
            # 1. Сбор всех доступных мест
            page.wait_for_selector("td[data-cost]", timeout=10000)
            cells = page.locator("td[data-cost]").all()

            if not cells:
                logger.info("No seats found")
                return False

            seats = []
            for el in cells:
                seats.append({
                    "r": int(el.get_attribute("data-row")),
                    "c": int(el.get_attribute("data-col")),
                    "el": el
                })

            def get_distance(s1, s2):
                # Вес ряда 1.5, чтобы горизонтальная близость была в приоритете
                return abs(s1["r"] - s2["r"]) * 1.5 + abs(s1["c"] - s2["c"])

            def count_islands(group):
                # Считаем, сколько в группе отдельных блоков (идущих подряд мест)
                if not group:
                    return 0
                count = 0
                coords = {(s["r"], s["c"]) for s in group}
                visited = set()
                for r, c in coords:
                    if (r, c) not in visited:
                        count += 1
                        # BFS для поиска связных мест (только по горизонтали)
                        q = deque([(r, c)])
                        while q:
                            curr_r, curr_c = q.popleft()
                            if (curr_r, curr_c) in visited:
                                continue
                            visited.add((curr_r, curr_c))
                            # Проверяем только соседей по горизонтали в том же ряду
                            for dc in [-1, 1]:
                                if (curr_r, curr_c + dc) in coords:
                                    q.append((curr_r, curr_c + dc))
                return count

            # 2. Генерируем лучшие группы для каждого сиденья как для "центра"
            candidates = []

            for root in seats:
                # Сортируем все остальные места по близости к текущему root
                others = sorted(seats, key=lambda x: get_distance(root, x))
                group = others[:NUMBER_OF_SEATS]  # Берем N ближайших

                if len(group) < NUMBER_OF_SEATS:
                    continue

                # Считаем штраф
                islands = count_islands(group)
                # Суммарное расстояние внутри группы (компактность)
                total_dist = sum(get_distance(group[0], s) for s in group)

                # Итоговый штраф: острова важнее всего (умножаем на 100)
                score = (islands * 100) + total_dist
                candidates.append({"score": score, "group": group})

            if not candidates:
                logger.info("Failed to collect group")
                return False

            # 3. Находим минимальный штраф и выбираем случайную группу из лучших
            min_score = min(c["score"] for c in candidates)
            best_candidates = [
                c for c in candidates if c["score"] == min_score]

            selected_group = random.choice(best_candidates)["group"]

            # 4. Кликаем
            # выводим лог с информацией о выбранных местах
            selected_group_rows_places = [
                f"Ряд {s['r']}, Место {s['c']}" for s in selected_group]
            print(
                f"Выбрано {len(selected_group)} мест. Выбранные места: {selected_group_rows_places}")
            for s in selected_group:
                s["el"].click()
                page.wait_for_timeout(200)

            # 4. Работа с чекбоксом "Принимаю условия"
            # Используем .check(), он сам проверит, нажат ли он уже
            accept_checkbox = page.locator("#accept")
            accept_checkbox.scroll_into_view_if_needed()
            accept_checkbox.check()

            # 5. Клик по кнопке "Оформить заказ"
            # Ждем, пока кнопка станет активной (так как чекбокс снимает disabled)
            btn_yes = page.locator("#btnYES")
            btn_yes.wait_for(state="visible")

            if btn_yes.is_enabled():
                btn_yes.click()
                logger.info("Order placed!")
                pause_self('ticket_reserver_bot')
            else:
                # Если вдруг кнопка все еще заблокирована, кликаем принудительно через JS
                logger.info("Button is blocked, trying to click forcibly...")
                btn_yes.dispatch_event("click")
                pause_self('ticket_reserver_bot')
            time.sleep(1)
            browser.close()
            msg = (f"Билеты Забронированы на логине {login}! Бот остановил работу, чтобы не дублировать заказы. Ссылка на постановку: {link}. "
                   )
            send_telegram_notification(msg)
            return True
    except Exception as e:
        logger.error(f"Error: {e}")
        pause_self('ticket_reserver_bot')
        return False


default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'retries': 0,  # Не ретраим внутри одного запуска, так как запуск каждую минуту
}


with DAG(
    'ticket_reserver_bot',
    default_args=default_args,
    description='Бот для покупки билетов каждую минуту',
    schedule_interval='* * * * *',  # Каждую минуту
    start_date=datetime(2026, 3, 20),
    catchup=False,  # Не догонять прошлые запуски
    max_active_runs=1,  # Только один запуск одновременно
) as dag:

    booking_step = PythonOperator(
        task_id='try_booking_tickets',
        python_callable=open_page_via_link,
        provide_context=True,
    )
