from loguru import logger


import glob
import importlib

import os

from importlib import reload

from ...registry import active_modules as modules


def load_module(modulename):
    try:
        logger.info(f'Loading module: {modulename}..')
        module = importlib.import_module('src.userbot.modules.extra.' + modulename)
        module = reload(module)
        cls = getattr(module, 'MatrixModule')
        return cls(modulename)
    except Exception:
        logger.exception(f'Module {modulename} failed to load')
        return None

from pathlib import Path

def get_modules():
    # 1. Находим папку 'extra' правильно
    # parents[1] поднимает нас из 'core' в 'modules', затем добавляем 'extra'
    extra_path = Path(__file__).resolve().parents[1] / 'extra'
    
    # 2. Ищем файлы именно в этой папке
    modulefiles = glob.glob(str(extra_path / "*.py"))
    
    # Отладка: покажет, что мы нашли
    logger.debug(f"Files found: {modulefiles}")

    for modulefile in modulefiles:
        modulename = os.path.splitext(os.path.basename(modulefile))[0]
        
        # Пропускаем __init__.py
        if modulename == "__init__":
            continue
            
        moduleobject = load_module(modulename)
        if moduleobject:
            # Сохраняем в реестр
            modules[modulename] = moduleobject
            logger.success(f"Module '{modulename}' is ready.")