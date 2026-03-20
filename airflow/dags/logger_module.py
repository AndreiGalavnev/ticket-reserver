import logging
import sys
import logging.handlers

# --- Logging Configuration ---


def setup_logging(
    logger_name: str = "my_app",  # Имя логгера
    log_file: str = "app.log",    # Имя файла лога
    level: int = logging.DEBUG,   # Общий уровень логгера
    console_level: int = logging.INFO,  # Уровень для вывода в консоль
    file_level: int = logging.DEBUG,   # Уровень для записи в файл
    max_bytes: int = 10 * 1024 * 1024,  # Макс. размер файла лога (10 MB)
    backup_count: int = 5,             # Количество бэкапов файла лога
    # Формат сообщений
    log_format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
) -> logging.Logger:
    """
    Настраивает и возвращает логгер с обработчиками для консоли и файла.

    Args:
        logger_name: Имя логгера.
        log_file: Путь к файлу лога.
        level: Минимальный уровень сообщений для обработки логгером.
        console_level: Минимальный уровень сообщений для вывода в консоль.
        file_level: Минимальный уровень сообщений для записи в файл.
        max_bytes: Максимальный размер файла лога перед ротацией.
        backup_count: Количество сохраняемых файлов бэкапа.
        log_format: Формат строки лога.

    Returns:
        Настроенный экземпляр logging.Logger.
    """
    logger = logging.getLogger(logger_name)

    # Предотвращаем добавление обработчиков, если логгер уже настроен
    if logger.hasHandlers():
        logger.warning(
            f"Logger '{logger_name}' already configured. Skipping setup.")
        return logger

    logger.setLevel(level)

    formatter = logging.Formatter(log_format)

    # --- Console Handler ---
    # Вывод в стандартный поток вывода (консоль)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # --- File Handler (Rotating) ---
    # Запись в файл с ротацией по размеру
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
        )
        file_handler.setLevel(file_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        # Если не удалось создать файловый обработчик, логируем ошибку в консоль и продолжаем без файла.
        logger.error(
            f"Failed to create file handler for {log_file}: {e}", exc_info=False)
        # вывод в stderr напрямую, если логгер еще не работает
        print(
            f"ERROR: Failed to create file handler for {log_file}: {e}", file=sys.stderr)

    # Обработка неперехваченных исключений

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            # Не логируем KeyboardInterrupt, позволяем Python обработать его штатно
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        # Логируем все остальные неперехваченные исключения
        logger.critical("Uncaught exception", exc_info=(
            exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    logger.info(f"Logger '{logger_name}' configured successfully. Logging to console (level {logging.getLevelName(console_level)}) and file '{log_file}' (level {logging.getLevelName(file_level)}).")

    return logger
