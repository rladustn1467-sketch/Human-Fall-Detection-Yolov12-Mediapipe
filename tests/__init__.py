# 낙상 판정 로직 테스트 (unittest, 추가 설치 없음)
# 실행: 프로젝트 폴더에서  venv\Scripts\python.exe -m unittest discover -s tests -t .
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
