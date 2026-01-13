import sys
from pathlib import Path
import runpy

if __name__ == '__main__':
    script_path = Path(__file__).with_name('aiogram_run.py')
    # Выполняем aiogram_run.py в том же интерпретаторе (и в venv локально)
    runpy.run_path(str(script_path), run_name='__main__')
